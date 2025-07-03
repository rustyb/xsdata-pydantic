from typing import Any, Dict
from typing import List
from typing import Optional

from xsdata.codegen.models import Class, Attr
from xsdata.formats.dataclass.filters import Filters
from xsdata.formats.dataclass.generator import DataclassGenerator
from xsdata.models.config import GeneratorConfig
from xsdata.utils.text import stop_words
from xsdata.models.enums import Tag

stop_words.update(["validate"])


class PydanticGenerator(DataclassGenerator):
    """Python pydantic dataclasses code generator."""

    @classmethod
    def init_filters(cls, config: GeneratorConfig) -> Filters:
        return PydanticFilters(config)


class PydanticFilters(Filters):
    def __init__(self, config: GeneratorConfig):
        config.output.format.kw_only = True
        super().__init__(config)
        self.default_class_annotation = None

    def post_meta_hook(self, obj: Class) -> Optional[str]:
        return "model_config = ConfigDict(defer_build=True, populate_by_name=True)"

    def class_bases(self, obj: Class, class_name: str) -> List[str]:
        result = super().class_bases(obj, class_name)

        if not obj.extensions:
            result.insert(0, "BaseModel")
        return result

    # Remove in favor of function below
    # def field_definition(
    #     self,
    #     obj: Class,
    #     attr: Attr,
    #     parent_namespace: Optional[str],
    # ) -> str:
    #     """Return the field definition with any extra metadata."""

    #     result = super().field_definition(obj, attr, parent_namespace)

    #     if attr.is_prohibited:
    #         result = result.replace("init=False", "exclude=True, default=None")
    #     elif attr.fixed:
    #         result = result.replace("init=False", "const=True")

    #     return result
    
    # Copy over the field definition function so can add extra key word args in before it
    # is converted to a string.
    def field_definition(
        self,
        obj: Class,
        attr: Attr,
        parent_namespace: Optional[str],
    ) -> str:
        """Return the field definition with any extra metadata."""
        ns_map = obj.ns_map
        default_value = super().field_default_value(attr, ns_map)
        metadata = super().field_metadata(obj, attr, parent_namespace)

        kwargs: dict[str, Any] = {}
        if attr.fixed or attr.is_prohibited:
            kwargs["init"] = False

            if attr.is_prohibited:
                kwargs[self.DEFAULT_KEY] = None

        if default_value is not False and not attr.is_prohibited:
            key = self.FACTORY_KEY if attr.is_factory else self.DEFAULT_KEY
            kwargs[key] = default_value

        ## TODO: could this be turned on or off via CLI / config option?
        if metadata:
            kwargs["metadata"] = metadata

            if metadata.get("name", None) is not None:
                kwargs["serialization_alias"]=metadata.get("name", None)
                kwargs["validation_alias"]=metadata.get("name", None)

        result = f"field({self.format_arguments(kwargs, 4)})"

        if attr.is_prohibited:
            result = result.replace("init=False", "exclude=True, default=None")
        elif attr.fixed:
            result = result.replace("init=False", "const=True")

        return result

    # Override the default field type methods to allow custom handling of the 
    # CIM types into pydantic types

    def field_type(self, obj: Class, attr: Attr) -> str:
        """Generate type hints for the given attr."""

        # print('CALLED FIELD TYPE obj =>', obj)
        print('CALLED FIELD TYPE att =>', attr)
        print(f"checking attname '{attr.qname}'")

       

        if attr.is_prohibited:
            return "Any"

        if attr.tag == Tag.CHOICE:
            return super().compound_field_types(obj, attr)

        result = super()._field_type_names(obj, attr, choice=False)
        
        ### Customization of default XML types to use custom models to keep validation intact.
        if attr.tag == "Element" and attr.name == "createdDateTime":
            print("CHECKING createdDateTime")
            r1 = super()._field_type_names(obj, attr, choice=False)
            print("CHECKING createdDateTime", r1, type(r1))
            result = 'ESMPDateTimeType'

        if attr.tag == "Element" and (attr.name == "start" or attr.name == "end"):
            print("CHECKING start/end")
            r1 = super()._field_type_names(obj, attr, choice=False)
            print("CHECKING start/end", r1, type(r1))
            result = 'YMDHMDateTimeType'

        if attr.types[0].qname == "{http://www.w3.org/2001/XMLSchema}duration":
            print("Setting type for xmlDuration to custom type")
            result = "ValidatedXmlDuration"
        

        iterable_fmt = super()._get_iterable_format()
        if attr.is_tokens:
            result = iterable_fmt.format(result)

        if attr.is_list:
            return iterable_fmt.format(result)

        if attr.is_tokens:
            return result

        if attr.is_dict:
            if super().generic_collections:
                return "Mapping[str, str]"

            return "dict[str, str]"

        if attr.is_nillable or (
            attr.default is None and (attr.is_optional or not super().format.kw_only)
        ):
            return f"None | {result}" if super().union_type else f"Optional[{result}]"

        return result
        
    @classmethod
    def build_import_patterns(cls) -> Dict[str, Dict]:
        patterns = super().build_import_patterns()
        type_patterns = cls.build_type_patterns
        patterns.update(
            {
                "dataclasses": {},
                "xsdata_pydantic.fields": {"field": [" = field("]},
                "pydantic": {
                    "BaseModel": ["(BaseModel"],
                    "Field": [" Field("],
                    "ConfigDict": ["model_config = ConfigDict("],
                },
                # Custom to support conversion of CIM xsd to pydantic classes
                "xsdata_pydantic.override_types": {
                    "ESMPDateTimeType": type_patterns("ESMPDateTimeType"),
                    "YMDHMDateTimeType": type_patterns("YMDHMDateTimeType"),
                    "ValidatedXmlDuration": type_patterns("ValidatedXmlDuration")
                }
            }
        )

        return {key: patterns[key] for key in sorted(patterns)}
