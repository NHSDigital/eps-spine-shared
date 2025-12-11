class EpsLogger:
    """
    Wrapper for logging to handle either EPS or Spine logger.
    """

    def __init__(self, logger=None):
        self.logger = logger
        self.is_spine = hasattr(logger, "writeLog")

    def write_log(self, code: str, exc_info, data: dict = None):
        if self.is_spine:
            self.logger.writeLog(code, exc_info, data)
        else:
            print({"code": code, "exc_info": exc_info, "data": data})
