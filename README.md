Fork of [**xsdata-pydantic**](https://github.com/dmfilipenko/xsdata-pydantic) to handle working with CIM xsd documents.

# xsdata-pydantic-cim

This is a tool which can be used for converting electricity CIM xsd models into somewhat usable pydantic models.

Current customizations are:

- add `serialization_alias` and `validation_alias` to fields generated with name in the metadata to preserve original field names when serialising to/from JSON.

- add custom types for the following elements:
    - `ESMPDateTimeType`
    - `YMDHMDateTimeType`
    - `ValidatedXmlDuration`


### Usage

When using the following annotated types are exported

```python
# Type aliases for easy use
ValidatedXmlDuration
ESMPDateTimeType = Annotated[datetime, ESMPDateTime]
YMDHMDateTimeType = Annotated[datetime, YMDHMDateTime]

```
