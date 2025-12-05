from eps_spine_shared.common.prescription.record import PrescriptionRecord


class RepeatPrescribeRecord(PrescriptionRecord):
    """
    Class defined to handle repeat prescribe prescriptions
    """

    def __init__(self, log_object, internal_id):
        """
        Allow the recordType attribute to be set
        """
        super(RepeatPrescribeRecord, self).__init__(log_object, internal_id)
        self.recordType = "RepeatPrescribe"
