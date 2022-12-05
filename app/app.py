import asyncio
import numpy as np
import bisect
import dearpygui.dearpygui as dpg

from binance_interface.rest.interface import Interface as Rest
from binance_interface.ws.interface import Interface_ws as Ws


def apply_update(orderbook_side, update):
    # orderbook_side : list //sorted

    for item in update:
        index = bisect.bisect_left(orderbook_side, [item[0], 0])

        if len(orderbook_side) == index or orderbook_side[index][0] != item[0]:
            if item[1] == 0:  # нужно чтобы можно было применять нулевой апдейт.
                continue
            orderbook_side.insert(index, item)

        elif orderbook_side[index][0] == item[0]:
            if item[1] == 0:
                del orderbook_side[index]
            else:
                orderbook_side[index] = item


NOT_REQUESTED = 'not_requested'
REQUESTED = 'requested'
RECEIVED = 'received'


class Exchange_interface:
    rest = Rest()
    ws = Ws()

    def __init__(self):
        self._init()

    def _init(self):
        self.market = None

        self.orderbook_callback = None
        self.orderbook_snapshot_state = NOT_REQUESTED
        self.orderbook_updates = []
        self.get_orderbook_task = None
        self.orderbook_up_sid = None

        self.trades_callback = None
        self.trades_snapshot_state = NOT_REQUESTED
        self.trades_updates = []
        self.get_trades_task = None
        self.trades_up_sid = None

        self.ohlcv_callback = None
        self.ohlcv_snapshot_state = NOT_REQUESTED
        self.ohlcv_updates = []
        self.get_ohlcv_task = None
        self.ohlcv_up_sid = None
        self.ohlcv_interval = None

    def _clear(self):
        if self.orderbook_up_sid:
            self.ws.close_stream(self.orderbook_up_sid)
            if self.get_orderbook_task:
                self.get_orderbook_task.cancel()

        if self.trades_up_sid:
            self.ws.close_stream(self.trades_up_sid)
            if self.get_trades_task:
                self.get_trades_task.cancel()

        if self.ohlcv_up_sid:
            self.ws.close_stream(self.ohlcv_up_sid)
            if self.get_ohlcv_task:
                self.get_ohlcv_task.cancel()

        self._init()

    async def get_markets(self):
        return await self.rest.get_markets()

    def set_market(self, market):
        self._clear()
        self.market = market

    def sub_orderbook(self, callback):
        self.orderbook_callback = callback
        self.orderbook_up_sid = self.ws.sub_orderbook_up(self.market, callback=self._orderbook_up_callback)

    def _orderbook_up_callback(self, msg):
        if msg['tp'] == 'data':
            if self.orderbook_snapshot_state == RECEIVED:

                self.orderbook_callback('update', msg['data'])

            elif self.orderbook_snapshot_state == REQUESTED:
                self.orderbook_updates.append(msg['data'])

        elif msg['tp'] == 'stream_state' and msg['state'] == 'success':
            # гарантии, что снимок полученный после сообщения "success"
            # будет соответвовать апдейтам, нет. Но в данном случае, в угоду
            # простоте решения этот случай не рассматривается.
            # еще потенциально после получения снимка, может прийти более раний апдейт.
            # это тоже игнорируется.
            self.get_orderbook_task = asyncio.create_task(self._get_orderbook())

    async def _get_orderbook(self):

        self.orderbook_snapshot_state = REQUESTED
        response = await self.rest.get_orderbook(self.market)
        orderbook_snapshot = response['data']
        orderbook_snapshot['bids'] = sorted(orderbook_snapshot['bids'])
        orderbook_snapshot['asks'] = sorted(orderbook_snapshot['asks'])

        for update in self.orderbook_updates:
            if update['id'] <= orderbook_snapshot['id']:
                continue

            # первый апдейт. нулевой апдейт может проскочить.
            if update['id_start'] <= orderbook_snapshot['id'] + 1 <= update['id']:
                apply_update(orderbook_snapshot['bids'], update['bids'])
                apply_update(orderbook_snapshot['asks'], update['asks'])
                orderbook_snapshot['id'] = update['id']

        self.orderbook_updates = []
        self.orderbook_callback('snapshot', orderbook_snapshot)
        self.orderbook_snapshot_state = RECEIVED

    def sub_ohlcv(self, callback, interval='5m'):

        if self.ohlcv_up_sid:
            self.ws.close_stream(self.ohlcv_up_sid)
            if self.get_ohlcv_task:
                self.get_ohlcv_task.cancel()

        self.ohlcv_callback = None
        # self.ohlcv_snapshot=None
        self.ohlcv_snapshot_state = NOT_REQUESTED
        self.ohlcv_updates = []
        self.get_ohlcv_task = None
        self.ohlcv_up_sid = None
        self.ohlcv_interval = None

        self.ohlcv_interval = interval
        self.ohlcv_callback = callback

        self.ohlcv_up_sid = self.ws.sub_ohlcv_up(self.market, interval=interval,
                                                 callback=self._ohlcv_up_callback)

    def _ohlcv_up_callback(self, msg):


        if msg['tp'] == 'data':
            if self.ohlcv_snapshot_state == RECEIVED:
                self.ohlcv_callback('update', msg['data'])

            elif self.orderbook_snapshot_state == REQUESTED:
                self.ohlcv_updates.append(msg['data'])

        elif msg['tp'] == 'stream_state' and msg['state'] == 'success':
            self.get_ohlcv_task = asyncio.create_task(self._get_ohlcv())

    async def _get_ohlcv(self):

        self.ohlcv_snapshot_state = REQUESTED
        response = await self.rest.get_ohlcv(self.market, interval=self.ohlcv_interval)
        ohlcv_snapshot = response['data']

        for update in self.ohlcv_updates:

            if update['open_time'] < ohlcv_snapshot[-1]['open_time']:
                continue

            elif update['open_time'] == ohlcv_snapshot[-1]['open_time']:
                if update['qv'] > ohlcv_snapshot[-1]['qv']:
                    ohlcv_snapshot[-1] = update
            else:
                ohlcv_snapshot.append(update)

        self.ohlcv_updates = []
        self.ohlcv_snapshot_state = RECEIVED
        self.ohlcv_callback('snapshot', ohlcv_snapshot)

    def sub_trades(self, callback):
        self.trades_callback = callback
        self.trades_up_sid = self.ws.sub_trades_up(self.market, callback=self._trades_up_callback)

    def _trades_up_callback(self, msg):

        if msg['tp'] == 'data':

            update = []
            for trade in msg['data']:
                update.append(
                    {
                        'id': trade['id'],
                        'tm': np.datetime64(trade['tm'], 'ms'),
                        'Q': trade['amount'],
                        'R': trade['price']
                    }
                )
            if self.trades_snapshot_state == RECEIVED:
                self.trades_callback('update', update)

            elif self.orderbook_snapshot_state == REQUESTED:
                self.trades_updates.append(update)

        elif msg['tp'] == 'stream_state' and msg['state'] == 'success':
            self.get_trades_task = asyncio.create_task(self._get_trades())

    async def _get_trades(self):
        self.ohlcv_snapshot_state = REQUESTED
        response = await self.rest.get_trades(self.market)
        trades_snapshot = response['data']

        for update in self.trades_updates:
            for trade in update:
                if trade['id'] <= trades_snapshot[-1]['id']:
                    continue
                trades_snapshot.append(trade)

        self.trades_updates = []
        self.trades_snapshot_state = RECEIVED
        self.trades_callback('snapshot', trades_snapshot)


trades_max = 50
market_default = "BTC-ETH"

change_market_queue = []
change_ohlcv_interval_queue = []
# change_market_queue = asyncio.Queue()
# change_ohlcv_interval_queue = asyncio.Queue()

ei = Exchange_interface()

ohlcv = {
    'dates': [],
    'opens': [],
    'closes': [],
    'lows': [],
    'highs': [],
    'values': []
}

orderbook = {
    'bids': [],
    'asks': []
}

trades = []


def ohlcv_callback(tp, data):

    if tp == 'update':
        if ohlcv['dates'][-1] == data['open_tm'] // 1000:
            ohlcv['dates'][-1] = data['open_tm'] // 1000
            ohlcv['opens'][-1] = data['o']
            ohlcv['closes'][-1] = data['c']
            ohlcv['lows'][-1] = data['l']
            ohlcv['highs'][-1] = data['h']
            ohlcv['values'][-1] = data['bv']
        else:
            ohlcv['dates'].append(data['open_tm'] // 1000)
            ohlcv['opens'].append(data['o'])
            ohlcv['closes'].append(data['c'])
            ohlcv['lows'].append(data['l'])
            ohlcv['highs'].append(data['h'])
            ohlcv['values'].append(data['bv'])

        update_ohlcv_window(ohlcv)

    elif tp == 'snapshot':
        ohlcv['dates'] = []
        ohlcv['opens'] = []
        ohlcv['closes'] = []
        ohlcv['lows'] = []
        ohlcv['highs'] = []
        ohlcv['values'] = []

        for cline in data:
            ohlcv['dates'].append(cline['open_tm'] // 1000)
            ohlcv['opens'].append(cline['o'])
            ohlcv['closes'].append(cline['c'])
            ohlcv['lows'].append(cline['l'])
            ohlcv['highs'].append(cline['h'])
            ohlcv['values'].append(cline['bv'])
        create_ohlcv_window(ohlcv)



def orderbook_callback(tp, data):

    if tp == 'update':
        apply_update(orderbook['bids'], data['bids'])
        apply_update(orderbook['asks'], data['asks'])
        update_orderbook_window(orderbook)

    elif tp == 'snapshot':
        orderbook['bids'] = data['bids']
        orderbook['asks'] = data['asks']
        create_orderbook_window(orderbook)



def trades_callback(tp, data):

    if tp == 'update':
        for trade in data:
            trades.append(trade)
            if len(trades) > trades_max:
                trades.pop(0)

        update_trades_window(trades)

    elif tp == 'snapshot':
        trades.clear()
        trades.extend(data[-trades_max:])
        create_trades_window(trades)



async def _change_market():
    while True:
        await asyncio.sleep(1 / 60)
        if change_market_queue:
            market = change_market_queue[-1]
            change_market_queue.clear()
            ei.set_market(market)

            ei.sub_ohlcv(callback=ohlcv_callback)
            ei.sub_trades(callback=trades_callback)
            ei.sub_orderbook(callback=orderbook_callback)

            update_markets_window(market)


def change_market(sender, app_data, user_data):
    '''
    callbacks set for buttons run on a different thread. 
    So I can't use anything in them that is related to my event loop.
    '''
    change_market_queue.append(user_data)



async def _change_ohlcv_interval():
    while True:
        await asyncio.sleep(1 / 60)
        if change_ohlcv_interval_queue:
            interval = change_ohlcv_interval_queue[-1]
            change_ohlcv_interval_queue.clear()
            ei.sub_ohlcv(callback=ohlcv_callback, interval=interval)


def change_ohlcv_interval(sender, app_data, user_data):
    change_ohlcv_interval_queue.append(user_data)


def create_markets_window(markets):
    with dpg.window(label="markets", pos=[0, 0], height=950, width=100):
        dpg.add_text(market_default, tag='selected_market')

        with dpg.table(header_row=True, no_host_extendX=True, delay_search=True,
                       borders_innerH=True, borders_outerH=True, borders_innerV=True,
                       borders_outerV=True, context_menu_in_body=True, row_background=True,
                       policy=dpg.mvTable_SizingFixedFit, height=-1, width=-1,
                       scrollY=True):
            dpg.add_table_column()
            for market in markets:
                with dpg.table_row():
                    dpg.add_button(label=market, small=True, user_data=market, callback=change_market)


def update_markets_window(selected_market):
    dpg.set_value('selected_market', selected_market)


def destroy_ohlcv_window():
    dpg.delete_item('ohlcv_window')


def create_ohlcv_window(ohlcv):
    '''
	data : dict // keys: ['dates', 'opens', 'closes', 'lows', 'highs', 'values']
	'''
    try:
        destroy_ohlcv_window()
    except:
        pass

    with dpg.window(label="ohlcv", pos=[100, 0], height=950, width=950, tag='ohlcv_window'):
        with dpg.group(horizontal=True):
            dpg.add_button(label="1m", callback=change_ohlcv_interval, user_data="1m")
            dpg.add_button(label="5m", callback=change_ohlcv_interval, user_data="5m")
            dpg.add_button(label="1d", callback=change_ohlcv_interval, user_data="1d")

        with dpg.subplots(2, 1, label='ohlcv', height=-1, width=-1, link_columns=True, row_ratios=[4.0, 1.0],
                          column_ratios=[1.0]):
            with dpg.plot():
                xaxis = dpg.add_plot_axis(dpg.mvXAxis, label="Date", time=True)
                with dpg.plot_axis(dpg.mvYAxis, label="Price"):
                    dpg.add_candle_series(ohlcv['dates'],
                                          ohlcv['opens'],
                                          ohlcv['closes'],
                                          ohlcv['lows'],
                                          ohlcv['highs'],
                                          time_unit=dpg.mvTimeUnit_Min, tag='ohlc')
                    dpg.fit_axis_data(dpg.top_container_stack())
                dpg.fit_axis_data(xaxis)

            with dpg.plot():
                xaxis = dpg.add_plot_axis(dpg.mvXAxis, label="Date", time=True)

                with dpg.plot_axis(dpg.mvYAxis, label="Value", log_scale=False):
                    dpg.add_bar_series(ohlcv['dates'], ohlcv['values'], weight=-1, tag='values')
                    dpg.fit_axis_data(dpg.top_container_stack())
                dpg.fit_axis_data(xaxis)


def update_ohlcv_window(ohlcv):
    dpg.set_value('ohlc', [
        ohlcv['dates'],
        ohlcv['opens'],
        ohlcv['closes'],
        ohlcv['lows'],
        ohlcv['highs'],
    ])
    dpg.set_value('values', [ohlcv['dates'], ohlcv['values']])


def destroy_orderbook_window():
    dpg.delete_item('orderbook_window')


def change_agg_level(sender, app_data, user_data):
    raise NotImplementedError


def create_orderbook_window(orderbook):
    try:
        destroy_orderbook_window()
    except:
        pass

    with dpg.window(label="orderbook", pos=[100 + 950, 0], height=950, width=300,
                    tag='orderbook_window'):
        with dpg.group(horizontal=True):
            dpg.add_text("aggregation level:")
            dpg.add_button(label="0", callback=change_agg_level, user_data=0)
            dpg.add_button(label="1", callback=change_agg_level, user_data=1)
            dpg.add_button(label="2", callback=change_agg_level, user_data=2)
            dpg.add_button(label="3", callback=change_agg_level, user_data=3)
            dpg.add_button(label="4", callback=change_agg_level, user_data=4)
            dpg.add_button(label="5", callback=change_agg_level, user_data=5)

        dpg.add_text('asks')
        with dpg.table(label='asks', header_row=True, row_background=True,
                       borders_innerH=True, borders_outerH=True, borders_innerV=True,
                       borders_outerV=True, delay_search=True, tag='asks'):

            dpg.add_table_column(label="price")
            dpg.add_table_column(label="volume")

            asks = list(reversed(orderbook['asks'][:17]))
            for position in asks:
                with dpg.table_row():
                    dpg.add_text(position[0])
                    dpg.add_text(position[1])

        dpg.add_text('bids')
        with dpg.table(label='bids', header_row=True, row_background=True,
                       borders_innerH=True, borders_outerH=True, borders_innerV=True,
                       borders_outerV=True, delay_search=True, tag='bids'):

            dpg.add_table_column(label="price")
            dpg.add_table_column(label="volume")

            bids = list(reversed(orderbook['bids'][-17:]))
            for position in bids:
                with dpg.table_row():
                    dpg.add_text(position[0])
                    dpg.add_text(position[1])


def update_orderbook_window(orderbook):
    for tag_item in dpg.get_item_children('asks')[1]:
        dpg.delete_item(tag_item)

    asks = list(reversed(orderbook['asks'][:17]))
    for position in asks:
        with dpg.table_row(parent='asks'):
            dpg.add_text(position[0])
            dpg.add_text(position[1])

    for tag_item in dpg.get_item_children('bids')[1]:
        dpg.delete_item(tag_item)

    bids = list(reversed(orderbook['bids'][-17:]))
    for position in bids:
        with dpg.table_row(parent='bids'):
            dpg.add_text(position[0])
            dpg.add_text(position[1])


def destroy_trades_window():
    dpg.delete_item('trades_window')


def create_trades_window(trades):
    try:
        destroy_trades_window()
    except:
        pass

    with dpg.window(label="trades", pos=[100 + 950 + 300, 0],
                    height=950, width=300, tag='trades_window'):
        with dpg.table(label='bids', header_row=True, row_background=True,
                       borders_innerH=True, borders_outerH=True, borders_innerV=True,
                       borders_outerV=True, delay_search=True, scrollY=True, tag='trades'):
            dpg.add_table_column(label="price")
            dpg.add_table_column(label="volume")
            dpg.add_table_column(label="time")

            for trade in reversed(trades):
                with dpg.table_row():
                    dpg.add_text(trade['R'])
                    dpg.add_text(trade['Q'])
                    dpg.add_text(str(trade['tm'])[-12:])


def update_trades_window(trades):
    for tag_item in dpg.get_item_children('trades')[1]:
        dpg.delete_item(tag_item)

    for trade in reversed(trades):
        with dpg.table_row(parent='trades'):
            dpg.add_text(trade['R'])
            dpg.add_text(trade['Q'])
            dpg.add_text(str(trade['tm'])[-12:])


async def start():
    dpg.create_context()

    markets = await ei.get_markets()
    # print(markets)
    markets = sorted(
        [market for market, item in markets['data'].items() if item['status'] == 'TRADING']
    )

    create_markets_window(markets)

    dpg.create_viewport(title='Trade', width=1550, height=950)
    dpg.setup_dearpygui()
    dpg.show_viewport()

    asyncio.create_task(_change_market())
    asyncio.create_task(_change_ohlcv_interval())
    change_market_queue.append(market_default)

    while dpg.is_dearpygui_running:
        # print(1)
        dpg.render_dearpygui_frame()
        await asyncio.sleep(1 / 60)

    dpg.destroy_context()


if __name__ == "__main__":
    asyncio.run(start())
