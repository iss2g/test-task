class Parsing_error(Exception):
	pass


class Unknown_market(Parsing_error):
	def __init__(self, market):
		self.market = market


class Unknown_msg_tp(Parsing_error):
	pass


class Unknown_data_tp(Parsing_error):
	pass


class Unknown_failure_tp(Parsing_error):
	pass
