from eps_spine_shared.common.prescription.record import PrescriptionRecord


class RepeatPrescribeRecord(PrescriptionRecord):
    """
    Class defined to handle repeat prescribe prescriptions
    """

    def __init__(self, logObject, internalID):
        """
        Allow the recordType attribute to be set
        """
        super(RepeatPrescribeRecord, self).__init__(logObject, internalID)
        self.recordType = "RepeatPrescribe"
