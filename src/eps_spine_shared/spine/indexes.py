from eps_spine_shared.common.indexes import EpsIndexFactory


class PrescriptionIndexFactory(EpsIndexFactory):
    """
    Wrapper class for backward compatibility with camelCase method names.
    Inherits from EpsIndexFactory and provides camelCase method signatures
    that delegate to the snake_case implementations.
    """

    def __init__(self, logObject, internalID, testPrescribingSites, nadReference):
        super().__init__(
            log_object=logObject,
            internal_id=internalID,
            test_prescribing_sites=testPrescribingSites,
            nad_reference=nadReference,
        )
        # Maintain backward compatibility with camelCase attributes
        self.logObject = logObject
        self.internalID = internalID
        self.testPrescribingSites = testPrescribingSites
        self.nadReference = nadReference

    # Override parent method with camelCase signature for backward compatibility
    def buildIndexes(self, context):
        """
        Create the index values to be used when storing the epsRecord.
        """
        return self.build_indexes(context)
