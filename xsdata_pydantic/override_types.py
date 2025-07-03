from datetime import datetime, timedelta, timezone
import re
from typing import Annotated, Any, Union
from pydantic import BeforeValidator, Field, GetCoreSchemaHandler, PlainSerializer, WithJsonSchema, WrapSerializer
from xsdata.models.datatype import XmlDuration
from pydantic_core import core_schema
from xsdata_pydantic.bindings import XmlSerializer

def isoformat_timedelta(value: timedelta) -> str:
        """Produce an ISO8601-style representation of this :py:class:`timedelta`"""
        assert value >= timedelta(0), f"cannot produce ISO format for negative {value!r}"
        if not value:
            return "P0D"
        if value.days % 7 == 0 and not value.seconds and not value.microseconds:
            return f"P{int(value.days / 7)}W"
        
        days = value.days
        minutes, seconds = divmod(value.seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if value.microseconds:
            seconds += value.microseconds / 1_000_000  # type: ignore

        if hours and days:
            hours += days * 24
            days %= 1
        if minutes and hours:
            minutes += hours * 60
            hours %= 1
        if seconds and minutes:
            seconds += minutes * 60
            minutes %= 1

        result = f"P{days}D" if days else "P"
        if hours or minutes or seconds:
            result += "T"
            result += f"{hours}H" if hours else ""
            result += f"{minutes}M" if minutes else ""
            result += f"{seconds:.6f}".rstrip("0").rstrip(".") + "S" if seconds else ""
        return result

def validate_xml_duration(value: Any) -> XmlDuration:
    """
    Validator function to convert string to XmlDuration.
    """
    if isinstance(value, str):
        try:
            return XmlDuration(value)
        except ValueError:
            raise ValueError(f"Invalid XmlDuration string format: '{value}'. Expected format like 'PT15M'.")
    # If it's already an XmlDuration object, or another type Pydantic can handle,
    # let Pydantic's default validation proceed.
    return value

def serialize_xml_duration_to_timedelta(xml_duration: XmlDuration) -> timedelta:
    """
    Converts XmlDuration to datetime.timedelta.
    (Approximates years/months to days)
    """
    total_days = 0
    if xml_duration.years is not None:
        total_days += xml_duration.years * 365
    if xml_duration.months is not None:
        total_days += xml_duration.months * 30
    if xml_duration.days is not None:
        total_days += xml_duration.days

    total_seconds = 0
    if xml_duration.hours is not None:
        total_seconds += xml_duration.hours * 3600
    if xml_duration.minutes is not None:
        total_seconds += xml_duration.minutes * 60
    if xml_duration.seconds is not None:
        total_seconds += xml_duration.seconds

    if xml_duration.negative:
        total_days *= -1
        total_seconds *= -1

    return timedelta(days=total_days, seconds=total_seconds)

# --- NEW: WrapSerializer for XmlDuration ---
def serialize_xml_duration_for_fastapi(
    value: XmlDuration,
    handler,
    info: Any # SerializationInfo can be used if you need context
) -> Any:
    """
    Wrap serializer for XmlDuration.
    
    When serializing to Python (e.g., model_dump()), it will return timedelta.
    When serializing to JSON (e.g., via FastAPI), it will return the string representation.
    """
    # Check the serialization mode to decide what to return
    # 'json' mode is typically used by FastAPI for HTTP responses
    if info.mode == 'json':
        print('JSON:CONVERTING TIMEDELTA TO STRING')
        # For JSON output, return the string representation
        return str(value)
    else:
        # For Python dict output (or other non-JSON modes), return timedelta
        return serialize_xml_duration_to_timedelta(value)
    
# Define the custom Annotated type
ValidatedXmlDuration = Annotated[
    XmlDuration,
    BeforeValidator(validate_xml_duration),
    # PlainSerializer(serialize_xml_duration_to_timedelta, return_type=timedelta), # <--- Here's the key change
    WrapSerializer(
        serialize_xml_duration_for_fastapi,
        when_used='always', # Always apply this serializer
        return_type=Any # The return type can vary based on mode
    ),
    # Add WithJsonSchema to describe the expected JSON format
    WithJsonSchema(
        {
            "type": "duration",
            "format": "string", # 'duration' is a common format for ISO 8601 durations
            "pattern": "^P(?!$)(?:\\d+Y)?(?:\\d+M)?(?:\\d+W)?(?:\\d+D)?(?:T(?!$)(?:\\d+H)?(?:\\d+M)?(?:\\d+(?:\\.\\d+)?S)?)?$",
            "description": "An ISO 8601 duration string (e.g., 'PT15M' for 15 minutes, 'P1Y2M10DT2H30M' for 1 year, 2 months, 10 days, 2 hours, 30 minutes)."
        },
        # mode='serialization' # 'validation' mode applies the schema when validating data
                          # 'serialization' mode applies the schema when serializing data (optional, but good for consistent docs)
    )
]


class ESMPDateTime:
    """Custom type for ESMP datetime format with seconds (YYYY-MM-DDTHH:MM:SSZ)"""
    
    PATTERN = r"((([0-9]{4})[\-](0[13578]|1[02])[\-](0[1-9]|[12][0-9]|3[01])|([0-9]{4})[\-]((0[469])|(11))[\-](0[1-9]|[12][0-9]|30))T(([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9])Z)|(([13579][26][02468][048]|[13579][01345789](0)[48]|[13579][01345789][2468][048]|[02468][048][02468][048]|[02468][1235679](0)[48]|[02468][1235679][2468][048]|[0-9][0-9][13579][26])[\-](02)[\-](0[1-9]|1[0-9]|2[0-9])T(([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9])Z)|(([13579][26][02468][1235679]|[13579][01345789](0)[01235679]|[13579][01345789][2468][1235679]|[02468][048][02468][1235679]|[02468][1235679](0)[01235679]|[02468][1235679][2468][1235679]|[0-9][0-9][13579][01345789])[\-](02)[\-](0[1-9]|1[0-9]|2[0-8])T(([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9])Z)"
    FORMAT = '%Y-%m-%dT%H:%M:%SZ'
    
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Define the core schema for Pydantic validation"""
        return core_schema.no_info_before_validator_function(
            cls._validate,
            core_schema.union_schema([
                core_schema.datetime_schema(),
                core_schema.str_schema(),
            ]),
            # CORRECTED LINE: Use plain_serializer_function
            serialization=core_schema.plain_serializer_function_ser_schema(
                cls._serialize,
                return_schema=core_schema.str_schema()
            ),
        )
    
    @classmethod
    def _validate(cls, value: Union[str, datetime]) -> datetime:
        """Validate and convert input to datetime"""
        # Generate a current example for error messages
        example_dt = datetime.now().strftime(cls.FORMAT)
        
        if isinstance(value, str):
            # Validate string against pattern
            if not re.match(cls.PATTERN, value):
                raise ValueError(
                    f"String '{value}' does not match the required datetime pattern. "
                    f"Expected format: YYYY-MM-DDTHH:MM:SSZ (example: '{example_dt}')"
                )
            # Parse the validated string
            try:
                return datetime.strptime(value, cls.FORMAT)
            except ValueError as e:
                raise ValueError(
                    f"Failed to parse datetime string '{value}'. "
                    f"Expected format: YYYY-MM-DDTHH:MM:SSZ (example: '{example_dt}')"
                ) from e
        elif isinstance(value, datetime):
            # Convert timezone-aware datetime to UTC
            if value.tzinfo is not None:
                # Use replace(tzinfo=None) to make it naive UTC
                value = value.astimezone(timezone.utc).replace(tzinfo=None)
            return value
        else:
            raise ValueError(
                f"Value must be a string matching the datetime pattern or a datetime object, got {type(value)}. "
                f"For strings, expected format: YYYY-MM-DDTHH:MM:SSZ (example: '{example_dt}')"
            )
    
    @classmethod
    def _serialize(cls, value: datetime) -> str:
        """Serialize datetime to string format"""
        if isinstance(value, datetime):
            return value.strftime(cls.FORMAT)
        # Fallback for unexpected types during serialization, though _validate should prevent this
        return str(value)


class YMDHMDateTime:
    """Custom type for ESMP datetime format without seconds (YYYY-MM-DDTHH:MMZ)"""
    
    PATTERN = r"((([0-9]{4})[\-](0[13578]|1[02])[\-](0[1-9]|[12][0-9]|3[01])|([0-9]{4})[\-]((0[469])|(11))[\-](0[1-9]|[12][0-9]|30))T(([01][0-9]|2[0-3]):[0-5][0-9])Z)|(([13579][26][02468][048]|[13579][01345789](0)[48]|[13579][01345789][2468][048]|[02468][048][02468][048]|[02468][1235679](0)[48]|[02468][1235679][2468][048]|[0-9][0-9][13579][26])[\-](02)[\-](0[1-9]|1[0-9]|2[0-9])T(([01][0-9]|2[0-3]):[0-5][0-9])Z)|(([13579][26][02468][1235679]|[13579][01345789](0)[01235679]|[13579][01345789][2468][1235679]|[02468][048][02468][1235679]|[02468][1235679](0)[01235679]|[02468][1235679][2468][1235679]|[0-9][0-9][13579][01345789])[\-](02)[\-](0[1-9]|1[0-9]|2[0-8])T(([01][0-9]|2[0-3]):[0-5][0-9])Z)"
    FORMAT = '%Y-%m-%dT%H:%MZ'
    
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Define the core schema for Pydantic validation"""
        return core_schema.no_info_before_validator_function(
            cls._validate,
            core_schema.union_schema([
                core_schema.datetime_schema(),
                core_schema.str_schema(),
            ]),
            # CORRECTED LINE: Use plain_serializer_function
            serialization=core_schema.plain_serializer_function_ser_schema(
                cls._serialize,
                return_schema=core_schema.str_schema()
            ),
        )
    
    @classmethod
    def _validate(cls, value: Union[str, datetime]) -> datetime:
        """Validate and convert input to datetime"""
        # Generate a current example for error messages
        example_dt = datetime.now().strftime(cls.FORMAT)
        
        if isinstance(value, str):
            # Validate string against pattern
            if not re.match(cls.PATTERN, value):
                raise ValueError(
                    f"String '{value}' does not match the required datetime pattern. "
                    f"Expected format: YYYY-MM-DDTHH:MMZ (example: '{example_dt}')"
                )
            # Parse the validated string
            try:
                return datetime.strptime(value, cls.FORMAT)
            except ValueError as e:
                raise ValueError(
                    f"Failed to parse datetime string '{value}'. "
                    f"Expected format: YYYY-MM-DDTHH:MMZ (example: '{example_dt}')"
                ) from e
        elif isinstance(value, datetime):
            # Convert timezone-aware datetime to UTC
            if value.tzinfo is not None:
                value = value.astimezone(timezone.utc).replace(tzinfo=None)
            return value
        else:
            raise ValueError(
                f"Value must be a string matching the datetime pattern or a datetime object, got {type(value)}. "
                f"For strings, expected format: YYYY-MM-DDTHH:MMZ (example: '{example_dt}')"
            )
    
    @classmethod
    def _serialize(cls, value: datetime) -> str:
        """Serialize datetime to string format"""
        if isinstance(value, datetime):
            return value.strftime(cls.FORMAT)
        return str(value)


# Type aliases for easy use
ESMPDateTimeType = Annotated[datetime, ESMPDateTime]
YMDHMDateTimeType = Annotated[datetime, YMDHMDateTime]

