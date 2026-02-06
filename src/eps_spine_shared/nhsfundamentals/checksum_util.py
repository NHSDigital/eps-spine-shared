from string import ascii_uppercase


class ChecksumUtil(object):
    """
    Provides utility methods for checkum validation
    """

    LONGIDLENGTH_WITH_CHECKDIGIT = 37
    SHORTIDLENGTH_WITH_CHECKDIGIT = 20

    def __init__(self, logObject):
        """
        :logObject required for logging invalid checksums
        """
        self.logObject = logObject

    def calculateChecksum(self, prescriptionID):
        """
        Generate a checksum for either R1 or R2 prescription
        """
        prscID = prescriptionID.replace("-", "")
        prscIDLength = len(prscID)

        runningTotal = 0
        for stringPosition in range(prscIDLength - 1):
            _charMod36 = int(prscID[stringPosition], 36)
            runningTotal += _charMod36 * (2 ** (prscIDLength - stringPosition - 1))

        checkValue = (38 - runningTotal % 37) % 37
        if checkValue == 36:
            checkValue = "+"
        elif checkValue > 9:
            checkValue = ascii_uppercase[checkValue - 10]
        else:
            checkValue = str(checkValue)

        return checkValue

    def checkChecksum(self, prescriptionID, internalID):
        """
        Check the checksum of a Prescription ID
        :prescriptionID the prescription to check
        :logObject optional logObject, if this is given then invalid checksums will be logged.
        """
        checkCharacter = prescriptionID[-1:]
        checkValue = self.calculateChecksum(prescriptionID)

        if checkValue == checkCharacter:
            return True

        self.logObject.writeLog(
            "MWS0042",
            None,
            dict(
                {
                    "internalID": internalID,
                    "prescriptionID": prescriptionID,
                    "checkValue": checkValue,
                }
            ),
        )

        return False

    @classmethod
    def removeCheckDigit(cls, prescriptionID):
        """
        Takes the passed in id and determines, by its length, if it contains a checkdigit,
        returns an id without the check digit
        """
        prescriptionKey = prescriptionID
        idLength = len(prescriptionID)
        if idLength in [cls.LONGIDLENGTH_WITH_CHECKDIGIT, cls.SHORTIDLENGTH_WITH_CHECKDIGIT]:
            prescriptionKey = prescriptionID[:-1]
        return prescriptionKey
