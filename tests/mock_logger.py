class MockLogObject(object):
    """
    Mock log object
    """

    def __init__(self, severity_threshold="INFO"):
        self._severity_threshold = severity_threshold
        self.logged_messages = []

    def write_log(
        self,
        log_reference="UTI9999",
        error_list=None,
        log_row_dict=None,
        severity_threshold_override=None,
        process_name=None,
    ):
        """
        Dummy write_log just keeps a list of the logReferences
        """
        log_row_dict = dict(log_row_dict) if log_row_dict else {}
        self.logged_messages.append((log_reference, log_row_dict))

    def get_log_occurrences(self, log_reference):
        """
        Gets a list of the args that were passed each time a specified message was logged
        """
        return [args for reference, args in self.logged_messages if reference == log_reference]

    @property
    def severity_threshold(self):
        """
        The severity threshold (ref logging.py _SEVERITY_INPUT_MAP)
        """
        return self._severity_threshold
