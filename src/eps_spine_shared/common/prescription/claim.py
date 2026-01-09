from eps_spine_shared.common.prescription import fields


class PrescriptionClaim(object):
    """
    Wrapper class to simplify interacting with an issue claim portion of a prescription record.
    """

    def __init__(self, claim_dict):
        """
        Constructor.

        :type claim_dict: dict
        """
        self._claim_dict = claim_dict

    @property
    def received_date_str(self):
        """
        The date the claim was received.

        :rtype: str
        """
        return self._claim_dict[fields.FIELD_CLAIM_RECEIVED_DATE]

    @received_date_str.setter
    def received_date_str(self, value):
        """
        The date the claim was received.

        :type value: str
        """
        self._claim_dict[fields.FIELD_CLAIM_RECEIVED_DATE] = value

    def get_dict(self):
        """
        returns claim_dict
        """
        return self._claim_dict
