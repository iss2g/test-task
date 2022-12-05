class LimitsError(Exception):
	pass


class CreateNotAllowed(LimitsError):
	pass


class ConnectNotAllowed(LimitsError):
	pass


class TimeoutError(LimitsError):
	pass


