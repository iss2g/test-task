import time
import numpy as np

def time_ms():
	return int(time.time() * 1000)


def time_s():
	return int(time.time())


s_per_unit = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def to_s(tm_label_less_s):
	if len(str(int(tm_label_less_s))) < 10:
		raise Exception('unintended for conversion')
	tm_label_less_s_str = str(tm_label_less_s)
	return int(tm_label_less_s_str[:10])


def td_to_sd(td):
	return int(td[:-1]) * s_per_unit[td[-1]]


def td_to_msd(td):
	return td_to_sd(td) * 1000


def round_dt64(dt64, around_to, direct='up', return_in='ms'):
    if not isinstance(around_to, str):
        raise Exception('around_to must be str like:1s, 3m, h ...')
    if around_to[0].isdigit() and int(around_to[0])==0:
        raise Exception('the numerical part of around_to must be a natural number or absent, not 0')
    dt64=np.datetime64(dt64, 'ms')

    dt64_down=np.datetime64(np.datetime64(dt64, around_to), return_in)
    
    if direct=='down':
        return dt64_down
    if direct=='up':
        
        if dt64==dt64_down:
            return dt64_down
        else:
            return np.datetime64(np.datetime64(dt64+np.timedelta64(1, around_to), around_to), return_in)


month_map = {
	"Jan": '01',
	"Feb": '02',
	"Mar": '03',
	"Apr": '04',
	"May": '05',
	"Jun": '06',
	"Jul": '07',
	"Aug": '08',
	"Sep": '09',
	"Oct": '10',
	"Nov": '11',
	"Dec": '12'
}


def dtHttp_to_dt64(http_date):
	_, day, month, year, time, _ = http_date.split(',')[1].split(' ')
	numMonth = month_map[month]
	return np.datetime64("%s-%s-%sT%s" % (year, numMonth, day, time))

