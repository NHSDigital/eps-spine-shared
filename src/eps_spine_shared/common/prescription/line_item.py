from eps_spine_shared.common.prescription import fields
from eps_spine_shared.common.prescription.statuses import LineItemStatus


class PrescriptionLineItem(object):
    """
    Wrapper class to simplify interacting with line item sections of a prescription record.
    """

    def __init__(self, line_item_dict):
        """
        Constructor.

        :type line_item_dict: dict
        """
        self._line_item_dict = line_item_dict

    @property
    def id(self):
        """
        The line item's ID.

        :rtype: str
        """
        return self._line_item_dict[fields.FIELD_ID]

    @property
    def status(self):
        """
        The status of this line item.

        :rtype: str
        """
        return self._line_item_dict[fields.FIELD_STATUS]

    @property
    def previous_status(self):
        """
        The previous status of this line item.

        :rtype: str
        """
        return self._line_item_dict[fields.FIELD_PREVIOUS_STATUS]

    @property
    def order(self):
        """
        The order of this line item.

        :rtype: int
        """
        return self._line_item_dict[fields.FIELD_ORDER]

    @property
    def max_repeats(self):
        """
        The maximum number of repeats for this line item.

        :rtype: int
        """
        return int(self._line_item_dict[fields.FIELD_MAX_REPEATS])

    def is_active(self):
        """
        Test whether this line item is active.

        :rtype: bool
        """
        return self.status in LineItemStatus.ACTIVE_STATES

    def update_status(self, new_status):
        """
        Set the line item status, and remember the previous status.

        :type new_status: str
        """
        self._line_item_dict[fields.FIELD_PREVIOUS_STATUS] = self._line_item_dict[
            fields.FIELD_STATUS
        ]
        self._line_item_dict[fields.FIELD_STATUS] = new_status

    def expire(self, parent_prescription):
        """
        Expire this line item.

        :type parent_prescription: PrescriptionRecord
        """
        currentStatus = self.status
        if currentStatus not in LineItemStatus.EXPIRY_IMMUTABLE_STATES:
            newStatus = LineItemStatus.EXPIRY_LOOKUP[currentStatus]
            self.update_status(newStatus)
            parent_prescription.logObject.writeLog(
                "EPS0072b",
                None,
                {
                    "internalID": parent_prescription.internalID,
                    "lineItemChanged": self.id,
                    "previousStatus": currentStatus,
                    "newStatus": newStatus,
                },
            )
