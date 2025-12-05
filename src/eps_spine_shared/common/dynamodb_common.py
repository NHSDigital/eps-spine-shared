import random
from decimal import Decimal
from enum import Enum
from typing import Optional


class ReleaseVersion(Enum):
    """
    Enum of release versions to be used in the DynamoDB table.
    """

    R1 = "R1"
    R2 = "R2"
    UNKNOWN = "UNKNOWN"


class DefinedAttributeType(Enum):
    """
    S/N type for a defined attribute
    """

    STRING = "S"
    NUMBER = "N"


class DefinedAttribute:
    """
    Definition of an attribute in the DynamoDB table.
    """

    def __init__(self, name: str, arg_type: DefinedAttributeType) -> None:
        self.name = name
        self.type = arg_type


class Key(Enum):
    """
    Enum of table Keys
    """

    PK = DefinedAttribute("pk", DefinedAttributeType.STRING)
    SK = DefinedAttribute("sk", DefinedAttributeType.STRING)

    @property
    def name(self) -> str:
        return self.value.name

    @property
    def attribute_type(self) -> DefinedAttributeType:
        return self.value.type


class Attribute(Enum):
    """
    Enum of Defined Attributes to be used in the DynamoDB table.
    """

    NHS_NUMBER = DefinedAttribute("nhsNumber", DefinedAttributeType.STRING)
    CREATION_DATETIME = DefinedAttribute("creationDatetime", DefinedAttributeType.STRING)
    PRESCRIBER_ORG = DefinedAttribute("prescriberOrg", DefinedAttributeType.STRING)
    DISPENSER_ORG = DefinedAttribute("dispenserOrg", DefinedAttributeType.STRING)
    NOMINATED_PHARMACY = DefinedAttribute("nominatedPharmacy", DefinedAttributeType.STRING)
    IS_READY = DefinedAttribute("isReady", DefinedAttributeType.NUMBER)
    NEXT_ACTIVITY = DefinedAttribute("nextActivity", DefinedAttributeType.STRING)
    NEXT_ACTIVITY_DATE = DefinedAttribute("nextActivityDate", DefinedAttributeType.STRING)
    DOC_REF_TITLE = DefinedAttribute("docRefTitle", DefinedAttributeType.STRING)
    CLAIM_NOTIFICATION_STORE_DATE = DefinedAttribute(
        "claimNotificationStoreDate", DefinedAttributeType.STRING
    )
    STORE_TIME = DefinedAttribute("storeTime", DefinedAttributeType.STRING)
    BACKSTOP_DELETE_DATE = DefinedAttribute("backstopDeleteDate", DefinedAttributeType.STRING)
    SEQUENCE_NUMBER = DefinedAttribute("sequenceNumber", DefinedAttributeType.NUMBER)
    SEQUENCE_NUMBER_NWSSP = DefinedAttribute("sequenceNumberNwssp", DefinedAttributeType.NUMBER)
    LM_DAY = DefinedAttribute("_lm_day", DefinedAttributeType.STRING)
    RIAK_LM = DefinedAttribute("_riak_lm", DefinedAttributeType.NUMBER)
    BATCH_CLAIM_ID = DefinedAttribute("batchClaimId", DefinedAttributeType.STRING)

    @property
    def name(self) -> str:
        return self.value.name

    @property
    def attribute_type(self) -> DefinedAttributeType:
        return self.value.type


class ProjectedAttribute(Enum):
    """
    Enum of Projected Attributes to be used in the DynamoDB table.
    """

    CLAIM_IDS = "claimIds"
    SCN = "scn"
    STATUS = "status"
    BODY = "body"
    INDEXES = "indexes"
    EXPIRE_AT = "expireAt"

    @property
    def name(self) -> str:
        return self.value


class SortKey(Enum):
    """
    Enum of SortKeys to be used in the DynamoDB table.
    """

    DOCUMENT = "DOC"
    RECORD = "REC"
    WORK_LIST = "WRK"
    CLAIM = "CLM"
    SEQUENCE_NUMBER = "SQN"


class Index:
    """
    Information on a GSI
    """

    def __init__(self, name: str, pk: Attribute, sk: Optional[Attribute]) -> None:
        self.name = name
        self.pk = pk
        self.sk = sk if sk else None


class GSI(Enum):
    """
    Enum of global secondary indexes of the DynamoDB table.
    """

    NHS_NUMBER_DATE = Index("nhsNumberDate", Attribute.NHS_NUMBER, Attribute.CREATION_DATETIME)
    PRESCRIBER_DATE = Index("prescriberDate", Attribute.PRESCRIBER_ORG, Attribute.CREATION_DATETIME)
    DISPENSER_DATE = Index("dispenserDate", Attribute.DISPENSER_ORG, Attribute.CREATION_DATETIME)
    NOMINATED_PHARMACY_STATUS = Index(
        "nominatedPharmacyStatus", Attribute.NOMINATED_PHARMACY, Attribute.IS_READY
    )
    CLAIM_ID = Index("claimId", Key.SK, Attribute.BATCH_CLAIM_ID)
    NEXT_ACTIVITY_DATE = Index(
        "nextActivityDate", Attribute.NEXT_ACTIVITY, Attribute.NEXT_ACTIVITY_DATE
    )
    STORE_TIME_DOC_REF_TITLE = Index(
        "storeTimeDocRefTitle", Attribute.DOC_REF_TITLE, Attribute.STORE_TIME
    )
    CLAIM_NOTIFICATION_STORE_TIME = Index(
        "claimNotificationStoreTime", Attribute.CLAIM_NOTIFICATION_STORE_DATE, Attribute.STORE_TIME
    )
    BACKSTOP_DELETE_DATE = Index("backstopDeleteDate", Key.SK, Attribute.BACKSTOP_DELETE_DATE)
    CLAIM_ID_SEQUENCE_NUMBER = Index("claimIdSequenceNumber", Attribute.SEQUENCE_NUMBER, None)
    CLAIM_ID_SEQUENCE_NUMBER_NWSSP = Index(
        "claimIdSequenceNumberNwssp", Attribute.SEQUENCE_NUMBER_NWSSP, None
    )
    LAST_MODIFIED = Index("lastModified", Attribute.LM_DAY, Attribute.RIAK_LM)

    @property
    def name(self) -> str:
        return self.value.name

    @property
    def pk(self) -> Attribute:
        return self.value.pk

    @property
    def sk(self) -> Optional[Attribute]:
        return self.value.sk


REGION_NAME = "eu-west-2"
SERVICE_NAME = "dynamodb"
CONDITION_EXPRESSION = (
    f"attribute_not_exists({Key.PK.name}) AND attribute_not_exists({Key.SK.name})"
)
LAST_MODIFIED_DAILY_PARTITIONS = 12
NEXT_ACTIVITY_DATE_PARTITIONS = 12
RELEASE_VERSION_PARTITIONS = 12


def replace_decimals(obj):
    """
    Utility function to replace any instances of Decimal type with int/float.
    """

    def handle_decimal(obj):
        return int(obj) if obj % 1 == 0 else float(obj)

    def handle_dict(obj):
        for k in obj:
            obj[k] = replace_decimals(obj[k])
        return obj

    def handle_list(obj):
        for i in range(len(obj)):
            obj[i] = replace_decimals(obj[i])
        return obj

    handlers = {Decimal: handle_decimal, dict: handle_dict, list: handle_list}

    return handlers.get(type(obj), lambda obj: obj)(obj)


def prescription_id_without_check_digit(prescription_id) -> str:
    """
    If length is > 36 then long prescription id with checksum so truncate to 36 characters.
    If length is > 19 and < 36 then short prescription id with checksum so truncate to 19 characters.
    """
    if len(prescription_id) > 36:
        return prescription_id[:36]
    elif len(prescription_id) > 19 and len(prescription_id) < 36:
        return prescription_id[:19]
    else:
        return prescription_id


def determine_release_version(prescription_id) -> str:
    """
    Determines the release version of a prescription based on the length of its id. Includes shard for indexing.
    """
    id_length = len(prescription_id_without_check_digit(prescription_id))
    shard = random.randint(1, RELEASE_VERSION_PARTITIONS)
    match id_length:
        case 36:
            return f"{ReleaseVersion.R1.value}.{shard}"
        case 19:
            return f"{ReleaseVersion.R2.value}.{shard}"
        case _:
            return ReleaseVersion.UNKNOWN.value
