# Тестовое задание

Для выполнения тестового задания мною был выбран binance.

## Общий механизм:
для того чтобы отобразить на странице с рыночными торгами интересующие нас данные, обменик
должен:
  - установить websocket соендинение и отправить запросы на подписки на апдейты
  - получить снимки через http Api (Rest Api)
  - синхронизировать снимки и апдейты, для отображения актуальной и корректой картины на рынке.

websocket api url:
**wss://stream.binance.com:9443**

http api url:
**https://api.binance.com**

Ниже будут описанны данные получаемые через Api binance, их содержимое и механизм синхронизации.
В качестве примера торговой пары используется BTC-USDT.

## Orderbook:
представляет собой список заявок на покупку и продажу.

![](https://github.com/iss2g/test-task/blob/main/images/orderbook.png)


### snapshot:
**запрос:**

GET /api/v3/depth

**параметры:**

параметр | обязательный 
------------ | ------------ |
symbol  | да |
limit  | нет | 

**пример запроса:**

**https://www.binance.com/api/v3/depth?symbol=BTCUSDT&limit=1000**

**ответ:**

```javascript
{
	"lastUpdateId":28627526746,         
	"bids":[
		["17119.65000000","0.00615000"],  // [price, quantity]
		["17119.60000000","0.00858000"],
		...
		
		],
	"asks":[
		["17119.88000000","0.03082000"],  // [price, quantity]
		["17120.00000000","0.00105000"],
		...
		]
}
```	

### updates:
**запрос:**

\<symbol\>@depth

**пример запроса:**

```javascript
{
	"method":"SUBSCRIBE",
	"params":[
		"btcusdt@depth"
		],
	"id":1
}
```

**ответ:**

```javascript
{
	"stream":"btcusdt@depth",             // Stream name
	"data":{                      
		"e":"depthUpdate",                  // Stream type
		"E":1670177958587,                  // Event time
		"s":"BTCUSDT",                      // Symbol
		"U":28627239094,                    // First update ID in event
		"u":28627239434,                    // Final update ID in event
		"b":[                               // Bids
			["17093.40000000","0.00000000"],  // [price, quantity]
			["17093.31000000","0.00000000"]   
			],
		"a":[                               // Asks
			["17093.29000000","0.00000000"],  // [price, quantity]
			["17093.32000000","0.00000000"]
			]
		}
}
```

**синхронизация:**

Для того чтобы получить книгу и поддерживать ее в актуальном состоянии
нужно подписаться на обновления через websocket, и, после того как апдейты начнут приходить, запросить через rest api
снимок книги.
затем среди полученных апдейтов нужно найти апдейт или дождаться апдейт, который бы удолетворял условию:

  **update[U] <= snapshot[lastUpdateId]+1 <=update[u]**.
  
 затем применить апдейт следуя следующим правилам:
  - если quantity==0 - удалить из книги соответствующую price запись
  - если quantity>0 - заменить соответствующую price запись, или, если ее нет, вставить.
 
## Aggregate Trades:
представляет собой список последних совершенных сделок. 
Агрегированные сделки составляются из сделок, совершенных одновременно по одной цене.

![](https://github.com/iss2g/test-task/blob/main/images/trades.png)

### snapshot:
**запрос:**

GET /api/v3/aggTrades

**параметры:**

Параметр | Обязательный 
------------ | ------------ 
symbol |  да 
fromId |  нет 
startTime | нет 
endTime |  нет
limit |  нет

**пример запроса:**

**https://www.binance.com/api/v1/aggTrades?limit=80&symbol=BTCUSDT**

**ответ:**

```javascript
[
	{
		"a":1957135337,         // Aggregate trade ID
		"p":"17119.85000000",   // Price
		"q":"3.71412000",       // Quantity
		"f":2286641728,         // First trade ID*
		"l":2286641729,         // Last trade ID*
		"T":1670178412001,      // Trade time
		"m":false,              // Is the buyer the market maker?*
		"M":true                // Was the trade the best price match? 
	},
	...
]

```	

### updates:
**запрос:**

\<symbol\>@aggTrade

**пример запроса:**

```javascript
{
	"method":"SUBSCRIBE",
	"params":[
		"btcusdt@aggTrade"
		],
	"id":1
}
```

**ответ:**

```javascript
{
	"stream":"btcusdt@aggTrade",    // Stream name
	"data":{
		"e":"aggTrade",               // Stream type
		"E":1670177958728,            // Event time*
		"s":"BTCUSDT",                // Symbol
		"a":1957113127,               // Aggregate trade ID
		"p":"17092.77000000",         // Price
		"q":"0.03511000",             // Quantity
		"f":2286614639,               // First trade ID*
		"l":2286614639,               // Last trade ID*
		"T":1670177958728,            // Trade time
		"m":true,                     // Is the buyer the market maker?*
		"M":true                      // Was the trade the best price match? 
		}
}
```
пояснения:
  - Event time - время, когда сообщение было сформированно.
  - First trade ID, Last trade ID - первый и последний id не агрегированных сделок, из которых была сформирована агрегированная сделка. 
  - Is the buyer the market maker? - этот элемент указывает на сторону сделки. При true: buy, при False: sell.

**синхронизация:**

Чтобы иметь последовательный и актуальный список торгов, нужно:
  - подписаться на апдейты через websocket.
  - получить список последних сделок через rest api.
  - добавлять в полученный список, сделки, полученные через websocket, Aggregate trade ID которых больше на 1 чем Aggregate trade ID последней сделки в списке. 

## Klines
Данные, из которых формируется OHCVL график.

![](https://github.com/iss2g/test-task/blob/main/images/ohlcv.png)


### snapshot:


### snapshot:
**запрос:**

GET /api/v3/uiKlines


**параметры:**

Параметр | Обязательный 
------------ | ------------ 
symbol |  да 
interval |  да 
startTime | нет 
endTime |  нет
limit |  нет

**пример запроса:**

**https://www.binance.com/api/v3/uiKlines?limit=1000&symbol=BTCUSDT&interval=1m**

**ответ:**

```javascript
[
	[
		1670118420000,        // Open time
		"16971.58000000",     // Open price
		"16978.10000000",     // Close price
		"16971.03000000",     // Low price
		"16974.96000000",     // High Price
		"94.44698000",        // Base asset volume (BTC)
		1670118479999,        // Close time
		"1603179.79037390",   // Quote asset volume (USDT)
		2615,                 // Number of trades
		"52.69512000",        // Taker buy base asset volume
		"894476.87334890",    // Taker buy quote asset volume
		"0"                   // Ignore
	],
	...
]
	
```	

### updates:
**запрос:**

\<symbol\>@kline_\<interval\>

**пример запроса:**

```javascript
{
	"method":"SUBSCRIBE",
	"params":[
		"btcusdt@kline_1m"
		],
	"id":1
}
```

**ответ:**

```javascript
{
	"stream":"btcusdt@kline_1m",  
	"data":{
		"e":"kline",
		"E":1670177959132,        // Event time
		"s":"BTCUSDT",            // Symbol
		"k":{
			"t":1670177940000,      // Open time
			"T":1670177999999,      // Close time
			"s":"BTCUSDT",          // Symbol
			"i":"1m",               // Interval
			"f":2286613761,         // First trade id
			"L":2286614640,         // Last trade id
			"o":"17098.36000000",   // Open Price
			"c":"17093.01000000",   // Close price
			"h":"17098.37000000",   // High Price
			"l":"17091.93000000",   // Low Price
			"v":"55.82150000",      // Base asset volume (BTC)
			"n":880,                // Number of trades
      "x":false,              // Is this kline closed?
			"q":"954233.87155500",  // Quote asset volume (USDT)
			"V":"31.29088000",      // Taker buy base asset volume
			"Q":"534887.08374920",  // Taker buy quote asset volume
			"B":"0"                 // Ignore
		}
	}
}
```

**синхронизация:**:
  - подписаться на апдейты через websocket.
  - получить список свечей через rest api.
  - до тех пор пока последняя свеча не закрыта, заменять ее свечой, приходящей в апдейтах.
  - следующая свеча после закрытой свечи, должда быть добавленна в список.

### Дополнительно:

Также я написал скрипт на Python, который отображает и обновляет данные, о которых было написанно выше.
Для создания GUI была использована библиотека DearPyGui. Для получения данных с binance используется моя библиотека "binance_interface", 
которую писал еще 2 года назад и по этой причине, прошу сильно не оценивать ее качество) Вместо этого предлагаю оценить код, который я предоставил в code-example, который новее. 

![](https://github.com/iss2g/test-task/blob/main/images/app.png)


