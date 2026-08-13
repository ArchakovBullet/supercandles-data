import json
import logging  # Р‘СѓРґРµРј РІРµСЃС‚Рё Р»РѕРі
from datetime import datetime, timedelta
from threading import Thread
from typing import Literal, Any
from uuid import uuid4  # РЈРЅРёРєР°Р»СЊРЅС‹Р№ РёРґРµРЅС‚РёС„РёРєР°С‚РѕСЂ РїРѕРґРїРёСЃРєРё
from zoneinfo import ZoneInfo  # Р’СЂРµРјРµРЅРЅРђСЏ Р·РѕРЅР°
from json import loads  # РџРѕР»СѓС‡Р°РµРј РѕС‚РІРµС‚С‹ РІ С„РѕСЂРјР°Рµ JSON

import keyring  # Р‘РµР·РѕРїР°СЃРЅРѕРµ С…СЂР°РЅРµРЅРёРµ С‚РѕСЂРіРѕРІРѕРіРѕ С‚РѕРєРµРЅР°
from requests import get  # Р—Р°РїСЂРѕСЃС‹ С‡РµСЂРµР· HTTP API
from websockets import Subprotocol  # РџСЂРѕС‚РѕРєРѕР» STOMP
from websockets.sync.client import connect  # РџРѕРґРєР»СЋС‡РµРЅРёРµ Рє СЃРµСЂРІРµСЂСѓ WebSockets РІ СЃРёРЅС…СЂРѕРЅРЅРѕРј СЂРµР¶РёРјРµ
from stomp.utils import Frame, convert_frame, parse_frame  # Р Р°Р±РѕС‚Р° СЃ СЃРµСЂРІРµСЂРѕРј WebSockets РїРѕ РїСЂРѕС‚РѕРєРѕР»Сѓ STOMP


class MOEXPy:
    """Р Р°Р±РѕС‚Р° СЃ Algopack API РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рё https://moexalgo.github.io/docs/api РёР· Python"""
    iss_server = 'https://iss.moex.com/iss'  # РЎРїСЂР°РІРѕС‡РЅРёРєРё РњРѕСЃР‘РёСЂР¶Рё (ISS)
    ws_server = 'wss://iss.moex.com/infocx/v3/websocket'  # РРЅС„РѕСЂРјР°С†РёРѕРЅРЅРѕ-СЃС‚Р°С‚РёСЃС‚РёС‡РµСЃРєРёР№ СЃРµСЂРІРµСЂ СЂР°СЃРїСЂРѕСЃС‚СЂР°РЅРµРЅРёСЏ Р±РёСЂР¶РµРІРѕР№ РёРЅС„РѕСЂРјР°С†РёРё РІ СЂРµР°Р»СЊРЅРѕРј РІСЂРµРјРµРЅРё (ISS+) РЅР° РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рµ
    api_server = 'https://apim.moex.com/iss'  # РђР»РіРѕРїР°Рє (ISS)
    engine_map = dict(stocks='eq', futures='fo', currency='fx')  # РџР»РѕС‰Р°РґРєРё РђР»РіРѕРїР°РєР°: РђРєС†РёРё/С„СЊСЋС‡РµСЂСЃС‹/РІС‹Р»СЋС‚Р°
    tz_msk = ZoneInfo('Europe/Moscow')  # РњРѕСЃРєРѕРІСЃРєР°СЏ Р‘РёСЂР¶Р° СЂР°Р±РѕС‚Р°РµС‚ РїРѕ РјРѕСЃРєРѕРІСЃРєРѕРјСѓ РІСЂРµРјРµРЅРё
    logger = logging.getLogger('MOEXPy')  # Р‘СѓРґРµРј РІРµСЃС‚Рё Р»РѕРі

    def __init__(self, token=None, login=None, passcode=None):
        """РРЅРёС†РёР°Р»РёР·Р°С†РёСЏ

        :param str token: РўРѕРєРµРЅ (ISS)
        :param str login: Р›РѕРіРёРЅ (ISS+)
        :param str passcode: РџР°СЂРѕР»СЊ (ISS+)
        """
        if token is None:  # Р•СЃР»Рё С‚РѕСЂРіРѕРІС‹Р№ С‚РѕРєРµРЅ РЅРµ СѓРєР°Р·Р°РЅ (Р·Р°РїСЂРѕСЃС‹ ISS)
            # РЎРЅР°С‡Р°Р»Р° РїСЂРѕР±СѓРµРј .env
            try:
                from dotenv import load_dotenv
                load_dotenv('/root/finlab/.env')
                token = __import__('os').getenv('MOEX_TOKEN')
                self.token = token
            except:
                pass
            if self.token is None:
                try:
                    self.token = self.get_long_token_from_keyring('MOEXPy', 'token')  # С‚Рѕ РїРѕР»СѓС‡Р°РµРј РµРіРѕ РёР· Р·Р°С‰РёС‰РµРЅРЅРѕРіРѕ С…СЂР°РЅРёР»РёС‰Р° РїРѕ С‡Р°СЃС‚СЏРј
                except:
                    self.token = None
        else:  # Р•СЃР»Рё СѓРєР°Р·Р°РЅ С‚РѕСЂРіРѕРІС‹Р№ С‚РѕРєРµРЅ
            self.token = token  # РўРѕСЂРіРѕРІС‹Р№ С‚РѕРєРµРЅ
            self.set_long_token_to_keyring('MOEXPy', 'token', self.token)  # РЎРѕС…СЂР°РЅСЏРµРј РµРіРѕ РІ Р·Р°С‰РёС‰РµРЅРЅРѕРµ С…СЂР°РЅРёР»РёС‰Рµ
        self.headers = {'Accept': 'application/json', 'Authorization': f'Bearer {self.token}'}  # Р—Р°РіРѕР»РѕРІРєРё РґР»СЏ Р·Р°РїСЂРѕСЃРѕРІ
        if login is None:  # Р•СЃР»Рё Р»РѕРіРёРЅ РЅРµ СѓРєР°Р·Р°РЅ (РїРѕРґРїРёСЃРєРё ISS+)
            self.login = self.get_long_token_from_keyring('MOEXPy', 'login')  # С‚Рѕ РїРѕР»СѓС‡Р°РµРј РµРіРѕ РёР· Р·Р°С‰РёС‰РµРЅРЅРѕРіРѕ С…СЂР°РЅРёР»РёС‰Р° РїРѕ С‡Р°СЃС‚СЏРј
            self.passcode = self.get_long_token_from_keyring('MOEXPy', 'passcode')  # С‚Р°РєР¶Рµ РїРѕР»СѓС‡Р°РµРј РїР°СЂРѕР»СЊ РёР· Р·Р°С‰РёС‰РµРЅРЅРѕРіРѕ С…СЂР°РЅРёР»РёС‰Р° РїРѕ С‡Р°СЃС‚СЏРј
        else:  # Р•СЃР»Рё СѓРєР°Р·Р°РЅ Р»РѕРіРёРЅ
            self.login = login  # Р›РѕРіРёРЅ
            self.set_long_token_to_keyring('MOEXPy', 'login', self.login)  # РЎРѕС…СЂР°РЅСЏРµРј РµРіРѕ РІ Р·Р°С‰РёС‰РµРЅРЅРѕРµ С…СЂР°РЅРёР»РёС‰Рµ
            self.passcode = passcode  # РџР°СЂРѕР»СЊ
            self.set_long_token_to_keyring('MOEXPy', 'passcode', self.passcode)  # РЎРѕС…СЂР°РЅСЏРµРј РµРіРѕ РІ Р·Р°С‰РёС‰РµРЅРЅРѕРµ С…СЂР°РЅРёР»РёС‰Рµ
        self.ws_socket = None  # РџРѕРґРєР»СЋС‡РµРЅРёСЏ Рє СЃРµСЂРІРµСЂСѓ WebSockets РїРѕРєР° РЅРµС‚

        # РЎРѕР±С‹С‚РёСЏ СЃРµСЂРІРµСЂР° WebSocket
        self.on_connected = Event()  # РџРѕРґРєР»СЋС‡РµРЅРёРµ
        self.on_error = Event()  # РћС€РёР±РєР°
        self.on_receipt = Event()
        self.on_message = Event()  # РЎРѕРѕР±С‰РµРЅРёРµ (РґР°РЅРЅС‹Рµ РїРѕРґРїРёСЃРєРё)
        self.on_reply = Event()
        self.on_closed = Event()  # РћС‚РєР»СЋС‡РµРЅРёРµ

        # РЎРїСЂР°РІРѕС‡РЅРёРєРё
        dict_data = get(f'{self.iss_server}/index.json').json()  # РџРѕР»СѓС‡Р°РµРј Рё СЂР°Р·Р±РёСЂР°РµРј РґР°РЅРЅС‹Рµ РІ С„РѕСЂРјР°С‚Рµ JSON
        engines_columns = dict_data['engines']['columns']  # РўРѕСЂРіРѕРІС‹Рµ РїР»РѕС‰Р°РґРєРё - РќР°Р·РІР°РЅРёСЏ РєРѕР»РѕРЅРѕРє
        engines_data = dict_data['engines']['data']  # РўРѕСЂРіРѕРІС‹Рµ РїР»РѕС‰Р°РґРєРё - Р”Р°РЅРЅС‹Рµ
        self.engines_dict = {row[engines_columns.index('id')]: {col: row[i] for i, col in enumerate(engines_columns) if col != 'id'} for row in engines_data}  # РЎРїСЂР°РІРѕС‡РЅРёРє РїРѕ РєР»СЋС‡Сѓ id
        markets_columns = dict_data['markets']['columns']  # Р С‹РЅРєРё - РќР°Р·РІР°РЅРёСЏ РєРѕР»РѕРЅРѕРє
        markets_data = dict_data['markets']['data']  # Р С‹РЅРєРё - Р”Р°РЅРЅС‹Рµ
        self.markets_dict = {row[markets_columns.index('id')]: {col: row[i] for i, col in enumerate(markets_columns) if col != 'id'} for row in markets_data}  # РЎРїСЂР°РІРѕС‡РЅРёРє РїРѕ РєР»СЋС‡Сѓ id
        boards_columns = dict_data['boards']['columns']  # Р РµР¶РёРјС‹ С‚РѕСЂРіРѕРІ - РќР°Р·РІР°РЅРёСЏ РєРѕР»РѕРЅРѕРє
        boards_data = dict_data['boards']['data']  # Р РµР¶РёРјС‹ С‚РѕСЂРіРѕРІ - Р”Р°РЅРЅС‹Рµ
        self.boards_dict = {row[boards_columns.index('boardid')]: {col: row[i] for i, col in enumerate(boards_columns) if col != 'boardid'} for row in boards_data}  # РЎРїСЂР°РІРѕС‡РЅРёРє РїРѕ РєР»СЋС‡Сѓ boardid

        self.subscriptions = {}  # РЎРїСЂР°РІРѕС‡РЅРёРє РїРѕРґРїРёСЃРѕРє

    # Real-time market data - РђРєС†РёРё - https://moexalgo.github.io/docs/api/real-time-market-data-Р°РєС†РёРё
    # Real-time market data - Р¤СЊСЋС‡РµСЂСЃС‹ - https://moexalgo.github.io/docs/api/real-time-market-data-С„СЊСЋС‡РµСЂСЃС‹

    def get_all_tickers(self, board):
        """РўРѕСЂРіРѕРІР°СЏ СЃС‚Р°С‚РёСЃС‚РёРєР° Р·Р° СЃРµРіРѕРґРЅСЏ РїРѕ РІСЃРµРј РёРЅСЃС‚СЂСѓРјРµРЅС‚Р°Рј СЂРµР¶РёРјР° С‚РѕСЂРіРѕРІ

        param str board: Р РµР¶РёРј С‚РѕСЂРіРѕРІ
        """
        market, _, engine = self.get_market_engine(board)  # РџРѕ СЂРµР¶РёРјСѓ С‚РѕСЂРіРѕРІ РїРѕР»СѓС‡Р°РµРј СЂС‹РЅРѕРє Рё С‚РѕСЂРіРѕРІСѓСЋ РїР»РѕС‰Р°РґРєСѓ
        if market is None:  # Р•СЃР»Рё СЂС‹РЅРѕРє РЅРµ РїСЂРёС€РµР»
            return None  # С‚Рѕ РІС‹С…РѕРґРёРј, РґР°Р»СЊС€Рµ РЅРµ РїСЂРѕРґРѕР»Р¶Р°РµРј
        url = f'{self.iss_server}/engines/{engine}/markets/{market}/boards/{board}/securities.json'  # URL Р·Р°РїСЂРѕСЃР°
        start = 0  # РќР°С‡РёРЅР°РµРј РїРѕР»СѓС‡Р°С‚СЊ РґР°РЅРЅС‹Рµ СЃ РїРµСЂРІРѕР№ Р·Р°РїРёСЃРё РёРЅС‚РµСЂРІР°Р»Р°
        all_data = None  # РќР°РєРѕРїР»РµРЅРЅС‹Рµ РґР°РЅРЅС‹Рµ
        while True:  # РџРѕРєР° РЅРµ РѕР±СЂР°Р±РѕС‚Р°РµРј РІСЃРµ РїРµСЂРёРѕРґС‹ Р·Р°РїСЂРѕСЃР°
            params = {
                'start': start   # РќРѕРјРµСЂ РїРµСЂРІРѕР№ Р·Р°РїРёСЃРё СЃ РЅР°С‡Р°Р»Р° РёРЅС‚РµСЂРІР°Р»Р°
            }
            content = self.check_result(get(url, params=params, headers=self.headers))  # РћС‚РїСЂР°РІР»СЏРµРј Р·Р°РїСЂРѕСЃ, РїРѕР»СѓС‡Р°РµРј РѕС‚РІРµС‚
            if content is None:  # Р•СЃР»Рё РѕС‚РІРµС‚ РЅРµ РїСЂРёС€РµР»
                return None  # С‚Рѕ РІС‹С…РѕРґРёРј, РґР°Р»СЊС€Рµ РЅРµ РїСЂРѕРґРѕР»Р¶Р°РµРј
            data = content['securities']['data']  # РџСЂРёС€РµРґС€РёРµ РґР°РЅРЅС‹Рµ
            if len(data) == 0:  # Р•СЃР»Рё РґР°РЅРЅС‹С… РЅРµС‚ (РґРѕСЃС‚РёРіРЅСѓС‚ РєРѕРЅРµС† РІС‹Р±РѕСЂРєРё)
                break  # С‚Рѕ РІС‹С…РѕРґРёРј
            if all_data is None:  # Р•СЃР»Рё СЌС‚Рѕ РїРµСЂРІС‹Рµ РїСЂРёС€РµРґС€РёРµ РґР°РЅРЅС‹Рµ
                all_data = content  # С‚Рѕ СЃРѕС…СЂР°РЅСЏРµРј РёС… РїРѕР»РЅРѕСЃС‚СЊСЋ
            else:  # Р•СЃР»Рё РґР°РЅРЅС‹Рµ СѓР¶Рµ РµСЃС‚СЊ
                all_data['securities']['data'].extend(data)  # С‚Рѕ РґРѕР±Р°РІР»СЏРµРј Рє СѓР¶Рµ РёРјРµСЋС‰РёРјСЃСЏ
            start += len(data)  # РќРѕРјРµСЂ РїРµСЂРІРѕР№ Р·Р°РїРёСЃРё РїРµСЂРµРјРµС‰Р°РµРј Р·Р° РїРѕСЃР»РµРґРЅСЋСЋ РїРѕР»СѓС‡РµРЅРЅСѓСЋ
        return all_data

    def get_ticker(self, board, ticker):
        """РўРѕСЂРіРѕРІР°СЏ СЃС‚Р°С‚РёСЃС‚РёРєР° Р·Р° СЃРµРіРѕРґРЅСЏ РїРѕ РёРЅСЃС‚СЂСѓРјРµРЅС‚Сѓ

        param str board: Р РµР¶РёРј С‚РѕСЂРіРѕРІ
        param str ticker: РўРёРєРµСЂ
        """
        market, _, engine = self.get_market_engine(board)  # РџРѕ СЂРµР¶РёРјСѓ С‚РѕСЂРіРѕРІ РїРѕР»СѓС‡Р°РµРј СЂС‹РЅРѕРє Рё С‚РѕСЂРіРѕРІСѓСЋ РїР»РѕС‰Р°РґРєСѓ
        if market is None:  # Р•СЃР»Рё СЂС‹РЅРѕРє РЅРµ РїСЂРёС€РµР»
            return None  # С‚Рѕ РІС‹С…РѕРґРёРј, РґР°Р»СЊС€Рµ РЅРµ РїСЂРѕРґРѕР»Р¶Р°РµРј
        url = f'{self.iss_server}/engines/{engine}/markets/{market}/boards/{board}/securities/{ticker}.json'  # URL Р·Р°РїСЂРѕСЃР°
        return self.check_result(get(url, headers=self.headers))

    def get_candles(self, board, ticker, dt_from, dt_till, interval):
        """РЎРІРµС‡Рё РїРѕ РёРЅСЃС‚СЂСѓРјРµРЅС‚Сѓ

        param str board: Р РµР¶РёРј С‚РѕСЂРіРѕРІ
        param str ticker: РўРёРєРµСЂ
        param datetime dt_from: Р”Р°С‚Р° Рё РІСЂРµРјСЏ РЅР°С‡Р°Р»Р° Р·Р°РїСЂРѕСЃР°
        param datetime dt_till: Р”Р°С‚Р° Рё РІСЂРµРјСЏ РѕРєРѕРЅС‡Р°РЅРёСЏ Р·Р°РїСЂРѕСЃР°
        param int interval: Р’СЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р». 1 - 'M1', 10 - 'M10', 60 - 'M60', 24 - 'D1', 7 - 'W1', 31 - 'MN1', 4 - 'MN3'
        """
        market, _, engine = self.get_market_engine(board)  # РџРѕ СЂРµР¶РёРјСѓ С‚РѕСЂРіРѕРІ РїРѕР»СѓС‡Р°РµРј СЂС‹РЅРѕРє Рё С‚РѕСЂРіРѕРІСѓСЋ РїР»РѕС‰Р°РґРєСѓ
        if market is None:  # Р•СЃР»Рё СЂС‹РЅРѕРє РЅРµ РїСЂРёС€РµР»
            return None  # С‚Рѕ РІС‹С…РѕРґРёРј, РґР°Р»СЊС€Рµ РЅРµ РїСЂРѕРґРѕР»Р¶Р°РµРј
        url = f'{self.iss_server}/engines/{engine}/markets/{market}/boards/{board}/securities/{ticker}/candles.json'  # URL Р·Р°РїСЂРѕСЃР°
        all_data = None  # РќР°РєРѕРїР»РµРЅРЅС‹Рµ РґР°РЅРЅС‹Рµ
        while dt_from < dt_till:  # РџРѕРєР° РЅРµ РѕР±СЂР°Р±РѕС‚Р°РµРј РІСЃРµ РїРµСЂРёРѕРґС‹ Р·Р°РїСЂРѕСЃР°
            params = {
                'from': dt_from,  # Р”Р°С‚Р° Рё РІСЂРµРјСЏ РЅР°С‡Р°Р»Р° Р·Р°РїСЂРѕСЃР°
                'till': dt_till,  # Р”Р°С‚Р° Рё РІСЂРµРјСЏ РѕРєРѕРЅС‡Р°РЅРёСЏ Р·Р°РїСЂРѕСЃР°
                'interval': interval  # Р’СЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р»
            }
            content = self.check_result(get(url, params=params, headers=self.headers))  # РћС‚РїСЂР°РІР»СЏРµРј Р·Р°РїСЂРѕСЃ, РїРѕР»СѓС‡Р°РµРј РѕС‚РІРµС‚
            if content is None:  # Р•СЃР»Рё РѕС‚РІРµС‚ РЅРµ РїСЂРёС€РµР»
                return None  # С‚Рѕ РІС‹С…РѕРґРёРј, РґР°Р»СЊС€Рµ РЅРµ РїСЂРѕРґРѕР»Р¶Р°РµРј
            data = content['candles']['data']  # РџСЂРёС€РµРґС€РёРµ РґР°РЅРЅС‹Рµ
            if len(data) == 0:  # Р•СЃР»Рё РґР°РЅРЅС‹С… РЅРµС‚ (РґРѕСЃС‚РёРіРЅСѓС‚ РєРѕРЅРµС† РІС‹Р±РѕСЂРєРё)
                break  # С‚Рѕ РІС‹С…РѕРґРёРј
            if all_data is None:  # Р•СЃР»Рё СЌС‚Рѕ РїРµСЂРІС‹Рµ РїСЂРёС€РµРґС€РёРµ РґР°РЅРЅС‹Рµ
                all_data = content  # С‚Рѕ СЃРѕС…СЂР°РЅСЏРµРј РёС… РїРѕР»РЅРѕСЃС‚СЊСЋ
            else:  # Р•СЃР»Рё РґР°РЅРЅС‹Рµ СѓР¶Рµ РµСЃС‚СЊ
                all_data['candles']['data'].extend(data)  # С‚Рѕ РґРѕР±Р°РІР»СЏРµРј Рє СѓР¶Рµ РёРјРµСЋС‰РёРјСЃСЏ
            dt_from = datetime.strptime(data[-1][-2], '%Y-%m-%d %H:%M:%S') + timedelta(minutes=1)  # Р”Р°С‚Р° Рё РІСЂРµРјСЏ РЅР°С‡Р°Р»Р° СЃР»РµРґСѓСЋС‰РµРіРѕ РїРµСЂРёРѕРґР°
        return all_data

    def get_orderbook(self, board, ticker):
        """РЎС‚Р°РєР°РЅ РєРѕС‚РёСЂРѕРІРѕРє РїРѕ РёРЅСЃС‚СЂСѓРјРµРЅС‚Сѓ

        param str board: Р РµР¶РёРј С‚РѕСЂРіРѕРІ
        param str ticker: РўРёРєРµСЂ
        """
        market, _, engine = self.get_market_engine(board)  # РџРѕ СЂРµР¶РёРјСѓ С‚РѕСЂРіРѕРІ РїРѕР»СѓС‡Р°РµРј СЂС‹РЅРѕРє Рё С‚РѕСЂРіРѕРІСѓСЋ РїР»РѕС‰Р°РґРєСѓ
        if market is None:  # Р•СЃР»Рё СЂС‹РЅРѕРє РЅРµ РїСЂРёС€РµР»
            return None  # С‚Рѕ РІС‹С…РѕРґРёРј, РґР°Р»СЊС€Рµ РЅРµ РїСЂРѕРґРѕР»Р¶Р°РµРј
        url = f'{self.iss_server}/engines/{engine}/markets/{market}/boards/{board}/securities/{ticker}/orderbook.json'  # URL Р·Р°РїСЂРѕСЃР°
        return self.check_result(get(url, headers=self.headers))

    def get_trades(self, board, ticker, tradeno=None):
        """Р’СЃРµ СЃРґРµР»РєРё РїРѕ РёРЅСЃС‚СЂСѓРјРµРЅС‚Сѓ

        param str board: Р РµР¶РёРј С‚РѕСЂРіРѕРІ
        param str ticker: РўРёРєРµСЂ
        param int tradeno: РџРѕР»СѓС‡РёС‚СЊ СЃРґРµР»РєРё, РєРѕС‚РѕСЂС‹Рµ РёРґСѓС‚ РЅР°С‡РёРЅР°СЏ СЃ СѓРєР°Р·Р°РЅРЅРѕРіРѕ РЅРѕРјРµСЂР°
        """
        market, _, engine = self.get_market_engine(board)  # РџРѕ СЂРµР¶РёРјСѓ С‚РѕСЂРіРѕРІ РїРѕР»СѓС‡Р°РµРј СЂС‹РЅРѕРє Рё С‚РѕСЂРіРѕРІСѓСЋ РїР»РѕС‰Р°РґРєСѓ
        if market is None:  # Р•СЃР»Рё СЂС‹РЅРѕРє РЅРµ РїСЂРёС€РµР»
            return None
        url = f'{self.iss_server}/engines/{engine}/markets/{market}/boards/{board}/securities/{ticker}/trades.json'  # URL Р·Р°РїСЂРѕСЃР°
        params = {} if tradeno is None else dict(tradeno=tradeno)  # Р•СЃР»Рё СѓРєР°Р·Р°РЅ РЅРѕРјРµСЂ СЃРґРµР»РєРё, С‚Рѕ Р±СѓРґРµРј РїРѕР»СѓС‡Р°С‚СЊ СЃРґРµР»РєРё РЅР°С‡РёРЅР°СЏ СЃ СѓРєР°Р·Р°РЅРЅРѕРіРѕ РЅРѕРјРµСЂР°
        return self.check_result(get(url, params=params, headers=self.headers))

    # Super Candles - РђРєС†РёРё - https://moexalgo.github.io/docs/api/super-candles-Р°РєС†РёРё
    # Super Candles - Р¤СЊСЋС‡РµСЂСЃС‹ - https://moexalgo.github.io/docs/api/super-candles-С„СЊСЋС‡РµСЂСЃС‹
    # Super Candles - Р’Р°Р»СЋС‚Р° - https://moexalgo.github.io/docs/api/super-candles-РІР°Р»СЋС‚Р°

    def get_all_stats(self, stats: Literal['trade', 'ob', 'order'], engine: Literal['stock', 'futures', 'currency'], date, latest=False, limit=1000):
        """РњРµС‚СЂРёРєРё СЂР°СЃСЃС‡РёС‚Р°РЅРЅС‹Рµ РЅР° РѕСЃРЅРѕРІРµ РїРѕС‚РѕРєР° СЃРґРµР»РѕРє/РєРѕС‚РёСЂРѕРІРѕРє/Р·Р°СЏРІРѕРє РїРѕ РІСЃРµРј РёРЅСЃС‚СЂСѓРјРµРЅС‚Р°Рј

        :param Literal['trade', 'ob', 'order'] stats: РџРѕС‚РѕРє СЃРґРµР»РѕРє/РєРѕС‚РёСЂРѕРІРѕРє/Р·Р°СЏРІРѕРє
        :param Literal['stock', 'futures', 'currency'] engine: РўРѕСЂРіРѕРІР°СЏ РїР»РѕС‰Р°РґРєР° Р°РєС†РёР№/С„СЊСЋС‡РµСЂСЃРѕРІ/РІР°Р»СЋС‚
        :param date date: Р”Р°С‚Р° С‚РѕСЂРіРѕРІ
        :param bool latest: РџРѕСЃР»РµРґРЅСЏСЏ РїСЏС‚РёРјРёРЅСѓС‚РєР°
        :param int limit: РљРѕР»-РІРѕ Р·Р°РїРёСЃРµР№ (РЅРµ Р±РѕР»РµРµ 1000)
        """
        url = f'{self.api_server}/datashop/algopack/{self.engine_map[engine]}/{stats}stats.json'  # URL Р·Р°РїСЂРѕСЃР°
        params = dict(date=date, latest=latest, limit=limit)
        return self.check_result(get(url, params=params, headers=self.headers))

    def get_stats(self, stats: Literal['trade', 'ob', 'order'], engine: Literal['stock', 'futures', 'currency'], ticker, dt_from, dt_till, latest=False):
        """РњРµС‚СЂРёРєРё СЂР°СЃСЃС‡РёС‚Р°РЅРЅС‹Рµ РЅР° РѕСЃРЅРѕРІРµ РїРѕС‚РѕРєР° СЃРґРµР»РѕРє/РєРѕС‚РёСЂРѕРІРѕРє/Р·Р°СЏРІРѕРє РїРѕ РёРЅСЃС‚СЂСѓРјРµРЅС‚Сѓ

        :param Literal['trade', 'ob', 'order'] stats: РџРѕС‚РѕРє СЃРґРµР»РѕРє/РєРѕС‚РёСЂРѕРІРѕРє/Р·Р°СЏРІРѕРє
        :param Literal['stock', 'futures', 'currency'] engine: РўРѕСЂРіРѕРІР°СЏ РїР»РѕС‰Р°РґРєР° Р°РєС†РёР№/С„СЊСЋС‡РµСЂСЃРѕРІ/РІР°Р»СЋС‚
        :param str ticker: РўРёРєРµСЂ
        :param date dt_from: Р”Р°С‚Р° Рё РІСЂРµРјСЏ РЅР°С‡Р°Р»Р° Р·Р°РїСЂРѕСЃР°
        :param date dt_till: Р”Р°С‚Р° Рё РІСЂРµРјСЏ РѕРєРѕРЅС‡Р°РЅРёСЏ Р·Р°РїСЂРѕСЃР°
        :param bool latest: РџРѕСЃР»РµРґРЅСЏСЏ РїСЏС‚РёРјРёРЅСѓС‚РєР°
        """
        url = f'{self.api_server}/datashop/algopack/{self.engine_map[engine]}/{stats}stats/{ticker}.json'  # URL Р·Р°РїСЂРѕСЃР°
        all_data = None  # РќР°РєРѕРїР»РµРЅРЅС‹Рµ РґР°РЅРЅС‹Рµ
        while dt_from < dt_till:  # РџРѕРєР° РЅРµ РѕР±СЂР°Р±РѕС‚Р°РµРј РІСЃРµ РїРµСЂРёРѕРґС‹ Р·Р°РїСЂРѕСЃР°
            params = {
                'from': dt_from,  # Р”Р°С‚Р° Рё РІСЂРµРјСЏ РЅР°С‡Р°Р»Р° Р·Р°РїСЂРѕСЃР°
                'till': dt_till,  # Р”Р°С‚Р° Рё РІСЂРµРјСЏ РѕРєРѕРЅС‡Р°РЅРёСЏ Р·Р°РїСЂРѕСЃР°
                'latest': latest  # РџРѕСЃР»РµРґРЅСЏСЏ РїСЏС‚РёРјРёРЅСѓС‚РєР°
            }
            content = self.check_result(get(url, params=params, headers=self.headers))  # РћС‚РїСЂР°РІР»СЏРµРј Р·Р°РїСЂРѕСЃ, РїРѕР»СѓС‡Р°РµРј РѕС‚РІРµС‚
            if content is None:  # Р•СЃР»Рё РѕС‚РІРµС‚ РЅРµ РїСЂРёС€РµР»
                return None  # С‚Рѕ РІС‹С…РѕРґРёРј, РґР°Р»СЊС€Рµ РЅРµ РїСЂРѕРґРѕР»Р¶Р°РµРј
            data = content['candles']['data']  # РџСЂРёС€РµРґС€РёРµ РґР°РЅРЅС‹Рµ
            if len(data) == 0:  # Р•СЃР»Рё РґР°РЅРЅС‹С… РЅРµС‚ (РґРѕСЃС‚РёРіРЅСѓС‚ РєРѕРЅРµС† РІС‹Р±РѕСЂРєРё)
                break  # С‚Рѕ РІС‹С…РѕРґРёРј
            if all_data is None:  # Р•СЃР»Рё СЌС‚Рѕ РїРµСЂРІС‹Рµ РїСЂРёС€РµРґС€РёРµ РґР°РЅРЅС‹Рµ
                all_data = content  # С‚Рѕ СЃРѕС…СЂР°РЅСЏРµРј РёС… РїРѕР»РЅРѕСЃС‚СЊСЋ
            else:  # Р•СЃР»Рё РґР°РЅРЅС‹Рµ СѓР¶Рµ РµСЃС‚СЊ
                all_data['candles']['data'].extend(data)  # С‚Рѕ РґРѕР±Р°РІР»СЏРµРј Рє СѓР¶Рµ РёРјРµСЋС‰РёРјСЃСЏ
            dt_from = datetime.strptime(data[-1][-2], '%Y-%m-%d %H:%M:%S') + timedelta(minutes=1)  # Р”Р°С‚Р° Рё РІСЂРµРјСЏ РЅР°С‡Р°Р»Р° СЃР»РµРґСѓСЋС‰РµРіРѕ РїРµСЂРёРѕРґР°
        return all_data

    # Futures Open Interest (FUTOI) - https://moexalgo.github.io/docs/api/futures-open-interest-futoi

    def get_all_futoi(self, date):
        """Futures Open Interest (FUTOI) РїРѕ РІСЃРµРј РёРЅСЃС‚СЂСѓРјРµРЅС‚Р°Рј

        :param date date: Р”Р°С‚Р° С‚РѕСЂРіРѕРІ
        """
        url = f'{self.api_server}/analyticalproducts/futoi/securities.json'  # URL Р·Р°РїСЂРѕСЃР°
        start = 0  # РќР°С‡РёРЅР°РµРј РїРѕР»СѓС‡Р°С‚СЊ РґР°РЅРЅС‹Рµ СЃ РїРµСЂРІРѕР№ Р·Р°РїРёСЃРё
        all_data = None  # РќР°РєРѕРїР»РµРЅРЅС‹Рµ РґР°РЅРЅС‹Рµ
        while True:  # РџРѕРєР° РЅРµ РѕР±СЂР°Р±РѕС‚Р°РµРј РІСЃРµ РёРЅСЃС‚СЂСѓРјРµРЅС‚С‹
            params = {
                'date': date,  # Р”Р°С‚Р° С‚РѕСЂРіРѕРІ
                'start': start   # РќРѕРјРµСЂ РїРµСЂРІРѕР№ Р·Р°РїРёСЃРё СЃ РЅР°С‡Р°Р»Р° РёРЅС‚РµСЂРІР°Р»Р°
            }
            content = self.check_result(get(url, params=params, headers=self.headers))
            data = content['futoi']['data']  # РџСЂРёС€РµРґС€РёРµ РґР°РЅРЅС‹Рµ
            if len(data) == 0:  # Р•СЃР»Рё РґР°РЅРЅС‹С… РЅРµС‚ (РґРѕСЃС‚РёРіРЅСѓС‚ РєРѕРЅРµС† РІС‹Р±РѕСЂРєРё)
                break  # С‚Рѕ РІС‹С…РѕРґРёРј
            if all_data is None:  # Р•СЃР»Рё СЌС‚Рѕ РїРµСЂРІС‹Рµ РїСЂРёС€РµРґС€РёРµ РґР°РЅРЅС‹Рµ
                all_data = content  # С‚Рѕ СЃРѕС…СЂР°РЅСЏРµРј РёС… РїРѕР»РЅРѕСЃС‚СЊСЋ
            else:  # Р•СЃР»Рё РґР°РЅРЅС‹Рµ СѓР¶Рµ РµСЃС‚СЊ
                all_data['futoi']['data'].extend(data)  # С‚Рѕ РґРѕР±Р°РІР»СЏРµРј Рє СѓР¶Рµ РёРјРµСЋС‰РёРјСЃСЏ
            start += len(data)  # РќРѕРјРµСЂ РїРµСЂРІРѕР№ Р·Р°РїРёСЃРё РїРµСЂРµРјРµС‰Р°РµРј Р·Р° РїРѕСЃР»РµРґРЅСЋСЋ РїРѕР»СѓС‡РµРЅРЅСѓСЋ
        return all_data

    def get_futoi(self, ticker, dt_from, dt_till):
        """Futures Open Interest (FUTOI) РїРѕ РёРЅСЃС‚СЂСѓРјРµРЅС‚Сѓ

        :param str ticker: РўРёРєРµСЂ
        :param date dt_from: Р”Р°С‚Р° Рё РІСЂРµРјСЏ РЅР°С‡Р°Р»Р° Р·Р°РїСЂРѕСЃР°
        :param date dt_till: Р”Р°С‚Р° Рё РІСЂРµРјСЏ РѕРєРѕРЅС‡Р°РЅРёСЏ Р·Р°РїСЂРѕСЃР°
        """
        url = f'{self.api_server}/analyticalproducts/futoi/securities/{ticker}.json'  # URL Р·Р°РїСЂРѕСЃР°
        all_data = None  # РќР°РєРѕРїР»РµРЅРЅС‹Рµ РґР°РЅРЅС‹Рµ
        days = (dt_till - dt_from).days  # РџР°РіРёРЅР°С†РёСЏ РїРѕ С‚РѕСЂРіРѕРІС‹Рј СЃРµСЃСЃРёСЏРј
        for i in range(0, days + 1, 2):  # Р’ РєР°Р¶РґРѕРј Р·Р°РїСЂРѕСЃРµ, РіР°СЂР°РЅС‚РёСЂРѕРІР°РЅРЅРѕ, РІРјРµС‰Р°СЋС‚СЃСЏ 2 РґРЅСЏ
            params = {
                'from': dt_till - timedelta(days=i+1),  # Р”Р°С‚Р° Рё РІСЂРµРјСЏ РЅР°С‡Р°Р»Р° Р·Р°РїСЂРѕСЃР°
                'till': dt_till - timedelta(days=i),  # Р”Р°С‚Р° Рё РІСЂРµРјСЏ РѕРєРѕРЅС‡Р°РЅРёСЏ Р·Р°РїСЂРѕСЃР°
            }
            response = get(url, params=params, headers=self.headers)  # РћС‚РїСЂР°РІР»СЏРµРј Р·Р°РїСЂРѕСЃ, РїРѕР»СѓС‡Р°РµРј РѕС‚РІРµС‚
            content = loads(response.content.decode('utf-8'))  # Р РµР·СѓР»СЊС‚Р°С‚ Р·Р°РїСЂРѕСЃР° РІ РІРёРґРµ JSON
            data = [row for row in content['futoi']['data'] if dt_from <= datetime.strptime(f'{row[2]} {row[3]}', '%Y-%m-%d %H:%M:%S') <= dt_till]  # РџСЂРёС€РµРґС€РёРµ РґР°РЅРЅС‹Рµ СЃ С„РёР»СЊС‚СЂРѕРј РїРѕ РґР°С‚Рµ/РІСЂРµРјРµРЅРё Р·Р°РїСЂРѕСЃР°
            if all_data is None:  # Р•СЃР»Рё СЌС‚Рѕ РїРµСЂРІС‹Рµ РїСЂРёС€РµРґС€РёРµ РґР°РЅРЅС‹Рµ
                content['futoi']['data'] = data
                all_data = content  # С‚Рѕ СЃРѕС…СЂР°РЅСЏРµРј РёС… РїРѕР»РЅРѕСЃС‚СЊСЋ
            elif len(data) > 0:  # Р•СЃР»Рё РґР°РЅРЅС‹Рµ СѓР¶Рµ РµСЃС‚СЊ Рё РїСЂРёС€Р»Рё РЅРµ РїСѓСЃС‚С‹Рµ
                all_data['futoi']['data'].extend(data)  # С‚Рѕ РґРѕР±Р°РІР»СЏРµРј Рє СѓР¶Рµ РёРјРµСЋС‰РёРјСЃСЏ
        return all_data

    # Market Concentration (HI2) - https://moexalgo.github.io/docs/api/market-concentration-hi-2

    def get_all_hi2(self, engine: Literal['stock', 'futures', 'currency'], date):
        """РРЅРґРµРєСЃ СЂС‹РЅРѕС‡РЅРѕР№ РєРѕРЅС†РµРЅС‚СЂР°С†РёРё (РҐРµСЂС„РёРЅРґР°Р»СЏ-РҐРёСЂС€РјР°РЅР°) РїРѕ РІСЃРµРј РёРЅСЃС‚СЂСѓРјРµРЅС‚Р°Рј

        :param Literal['stock', 'futures', 'currency'] engine: РўРѕСЂРіРѕРІР°СЏ РїР»РѕС‰Р°РґРєР° Р°РєС†РёР№/С„СЊСЋС‡РµСЂСЃРѕРІ/РІР°Р»СЋС‚
        :param date date: Р”Р°С‚Р° С‚РѕСЂРіРѕРІ
        """
        url = f'{self.api_server}/datashop/algopack/{self.engine_map[engine]}/hi2.json'  # URL Р·Р°РїСЂРѕСЃР°
        params = dict(date=date)
        return self.check_result(get(url, params=params, headers=self.headers))

    def get_hi2(self, engine: Literal['stock', 'futures', 'currency'], ticker, date=None, from_date=None, till_date=None):
        """Индекс концентрации (Херфиндаля-Хиршмана) по инструменту
        :param engine: Торговая площадка
        :param ticker: Тикер
        :param date: Дата торгов (для обратной совместимости)
        :param from_date: Начало диапазона
        :param till_date: Конец диапазона
        """
        url = f'{self.api_server}/datashop/algopack/{self.engine_map[engine]}/hi2/{ticker}.json'
        params = {}
        if from_date and till_date:
            params['from'] = str(from_date)
            params['till'] = str(till_date)
        elif date:
            params['date'] = str(date)
        return self.check_result(get(url, params=params, headers=self.headers))

    # Mega Alerts - https://moexalgo.github.io/docs/api/mega-alerts

    def get_all_alerts(self, engine: Literal['stock', 'futures'], date):
        """РўРѕСЂРіРѕРІС‹Рµ Р°РЅРѕРјР°Р»РёРё РїРѕ РІСЃРµРј РёРЅСЃС‚СЂСѓРјРµРЅС‚Р°Рј

        :param Literal['stock', 'futures'] engine: РўРѕСЂРіРѕРІР°СЏ РїР»РѕС‰Р°РґРєР° Р°РєС†РёР№/С„СЊСЋС‡РµСЂСЃРѕРІ
        :param date date: Р”Р°С‚Р° С‚РѕСЂРіРѕРІ
        """
        url = f'{self.api_server}/datashop/algopack/{self.engine_map[engine]}/alerts.json'  # URL Р·Р°РїСЂРѕСЃР°
        params = dict(date=date)
        return self.check_result(get(url, params=params, headers=self.headers))

    def get_alerts(self, engine: Literal['stock', 'futures'], ticker, date):
        """РўРѕСЂРіРѕРІС‹Рµ Р°РЅРѕРјР°Р»РёРё РїРѕ РІСЃРµРј РёРЅСЃС‚СЂСѓРјРµРЅС‚Сѓ

        :param Literal['stock', 'futures'] engine: РўРѕСЂРіРѕРІР°СЏ РїР»РѕС‰Р°РґРєР° Р°РєС†РёР№/С„СЊСЋС‡РµСЂСЃРѕРІ
        :param str ticker: РўРёРєРµСЂ
        :param date date: Р”Р°С‚Р° С‚РѕСЂРіРѕРІ
        """
        url = f'{self.api_server}/datashop/algopack/{self.engine_map[engine]}/alerts/{ticker}.json'  # URL Р·Р°РїСЂРѕСЃР°
        params = dict(date=date)
        return self.check_result(get(url, params=params, headers=self.headers))

    # Р—Р°РїСЂРѕСЃС‹ REST

    def check_result(self, response):
        """РђРЅР°Р»РёР· СЂРµР·СѓР»СЊС‚Р°С‚Р° Р·Р°РїСЂРѕСЃР°

        :param Response response: Р РµР·СѓР»СЊС‚Р°С‚ Р·Р°РїСЂРѕСЃР°
        :return: РЎРїСЂР°РІРѕС‡РЅРёРє РёР· JSON, С‚РµРєСЃС‚, None РІ СЃР»СѓС‡Р°Рµ РІРµР± РѕС€РёР±РєРё
        """
        if response is None:  # Р•СЃР»Рё РѕС‚РІРµС‚ РЅРµ РїСЂРёС€РµР». РќР°РїСЂРёРјРµСЂ, РїСЂРё С‚Р°Р№РјР°СѓС‚Рµ
            self.logger.error('РћС€РёР±РєР° Р·Р°РїСЂРѕСЃР°: РўР°Р№РјР°СѓС‚')  # РЎРѕР±С‹С‚РёРµ РѕС€РёР±РєРё
            return None  # С‚Рѕ РІРѕР·РІСЂР°С‰Р°РµРј РїСѓСЃС‚РѕРµ Р·РЅР°С‡РµРЅРёРµ
        content = response.content.decode('utf-8')  # Р РµР·СѓР»СЊС‚Р°С‚ Р·Р°РїСЂРѕСЃР°
        if response.status_code != 200:  # Р•СЃР»Рё СЃС‚Р°С‚СѓСЃ РѕС€РёР±РєРё
            self.logger.error(f'РћС€РёР±РєР° Р·Р°РїСЂРѕСЃР°: {response.status_code} Р—Р°РїСЂРѕСЃ: {response.request.path_url} РћС‚РІРµС‚: {content}')  # РЎРѕР±С‹С‚РёРµ РѕС€РёР±РєРё
            return None  # С‚Рѕ РІРѕР·РІСЂР°С‰Р°РµРј РїСѓСЃС‚РѕРµ Р·РЅР°С‡РµРЅРёРµ
        self.logger.debug(f'Р—Р°РїСЂРѕСЃ : {response.request.path_url}')
        self.logger.debug(f'РћС‚РІРµС‚  : {content}')
        return loads(content)  # Р”РµРєРѕРґРёСЂСѓРµРј JSON РІ СЃРїСЂР°РІРѕС‡РЅРёРє, РІРѕР·РІСЂР°С‰Р°РµРј РµРіРѕ. РћС€РёР±РєРё С‚Р°РєР¶Рµ РјРѕРіСѓС‚ РїСЂРёС…РѕРґРёС‚СЊ РІ РІРёРґРµ JSON

    # Р—Р°РїСЂРѕСЃС‹ WebSocket

    def send_websocket(self, cmd: Literal['CONNECT', 'DISCONNECT', 'SUBSCRIBE', 'UNSUBSCRIBE', 'REQUEST', 'SEND'], params):
        """РћС‚РїСЂР°РІРєР° Р·Р°РїСЂРѕСЃР° С‡РµСЂРµР· РєРѕРјР°РЅРґРЅС‹Р№ WebSocket

        :param Literal['CONNECT', 'DISCONNECT', 'SUBSCRIBE', 'UNSUBSCRIBE', 'REQUEST', 'SEND'] cmd: РљР»РёРµРЅС‚СЃРєРёРµ РєРѕРјР°РЅРґС‹
        :param dict params: РџР°СЂР°РјРµС‚СЂС‹ Р·Р°РїСЂРѕСЃР° РІ РІРёРґРµ СЃР»РѕРІР°СЂСЏ
        """
        if self.ws_socket is None:  # Р•СЃР»Рё РЅРµ Р±С‹Р»Рѕ РїРѕРґРєР»СЋС‡РµРЅРёСЏ Рє СЃРµСЂРІРµСЂСѓ WebSocket
            self.ws_socket = connect(self.ws_server, subprotocols=[Subprotocol('STOMP')])  # С‚Рѕ РїСЂРѕР±СѓРµРј Рє РЅРµРјСѓ РїРѕРґРєР»СЋС‡РёС‚СЊСЃСЏ РїРѕ РїСЂРѕС‚РѕРєРѕР»Сѓ STOMP
            connect_request_frame = Frame(cmd='CONNECT', headers=dict(domain='passport', login=self.login, passcode=self.passcode))  # Р—Р°РїСЂРѕСЃ РЅР° Р°РІС‚РѕСЂРёР·Р°С†РёСЋ
            self.ws_socket.send(b''.join(convert_frame(connect_request_frame)))  # РћС‚РїСЂР°РІР»СЏРµРј
            connect_response_frame = parse_frame(self.ws_socket.recv())  # РћР¶РёРґР°РµРј Рё РїРѕР»СѓС‡Р°РµРј РѕС‚РІРµС‚
            if connect_response_frame.cmd != 'CONNECTED':  # Р•СЃР»Рё РЅРµ РїРѕРґРєР»СЋС‡РёР»РёСЃСЊ
                self.logger.error(f'РћС€РёР±РєР° РїРѕРґРєР»СЋС‡РµРЅРёСЏ Рє WebSocket: {connect_response_frame.cmd}')
                self.ws_socket = None  # РџРѕРґРєР»СЋС‡РµРЅРёСЏ Рє СЃРµСЂРІРµСЂСѓ WebSocket РЅРµС‚
                return  # Р’С‹С…РѕРґРёРј, РґР°Р»СЊС€Рµ РЅРµ РїСЂРѕРґРѕР»Р¶Р°РµРј
            else:  # Р•СЃР»Рё РїРѕРґРєР»СЋС‡РёР»РёСЃСЊ
                Thread(target=self.websocket_thread, name='WebSocketThread', daemon=True).start()  # РЎРѕР·РґР°РµРј Рё Р·Р°РїСѓСЃРєР°РµРј РїРѕС‚РѕРє СѓРїСЂР°РІР»РµРЅРёСЏ РїРѕРґРїРёСЃРєР°РјРё. Р—Р°РІРµСЂС€РёС‚СЃСЏ СЃ РѕРєРѕРЅС‡Р°РЅРёРµРј РѕСЃРЅРѕРІРЅРѕРіРѕ РїРѕС‚РѕРєР°
        if cmd == 'SUBSCRIBE':  # Р•СЃР»Рё РїРѕРґРїРёСЃС‹РІР°РµРјСЃСЏ
            subscription_id = str(uuid4())  # С‚Рѕ РіРµРЅРµСЂРёСЂСѓРµРј СѓРЅРёРєР°Р»СЊРЅС‹Р№ РЅРѕРјРµСЂ РїРѕРґРїРёСЃРєРё
            self.subscriptions[subscription_id] = params  # Р—Р°РЅРѕСЃРёРј РІ СЃРїРёСЃРѕРє РїРѕРґРїРёСЃРѕРє
            params['id'] = subscription_id  # РўР°РєР¶Рµ РїРµСЂРµРґР°РµРј РІ РїР°СЂР°РјРµС‚СЂС‹
        elif cmd == 'UNSUBSCRIBE':
            del self.subscriptions[params['id']]  # РЈРґР°Р»СЏРµРј РїРѕРґРїРёСЃРєСѓ РёР· СЃРїРёСЃРєР°
        request_frame = Frame(cmd=cmd, headers=params)  # РљР»РёРµРЅС‚СЃРєР°СЏ РєРѕРјР°РЅРґР° СЃ РїР°СЂР°РјРµС‚СЂР°РјРё
        self.logger.debug(f'РћС‚РїСЂР°РІР»РµРЅС‹ РґР°РЅРЅС‹Рµ WebSocket {request_frame.cmd} - {request_frame.body} - {request_frame.headers}')
        self.ws_socket.send(b''.join(convert_frame(request_frame)))  # РћС‚РїСЂР°РІР»СЏРµРј

    # РџРѕРґРїРёСЃРєРё WebSocket

    def websocket_thread(self):
        """РџРѕС‚РѕРє СѓРїСЂР°РІР»РµРЅРёСЏ РїРѕРґРїРёСЃРєР°РјРё"""
        self.logger.debug(f'WebSocket Thread: Р—Р°РїСѓС‰РµРЅ')
        while True:
            response_frame = parse_frame(self.ws_socket.recv())  # РџРѕР»СѓС‡Р°РµРј РѕС‚РІРµС‚ РёР»Рё С‚Р°Р№РјР°СѓС‚
            cmd = response_frame.cmd  # РџРѕР»СѓС‡РµРЅРЅР°СЏ РєРѕРјР°РЅРґР°
            headers = response_frame.headers  # Р—Р°РіРѕР»РѕРІРєРё РєРѕРјР°РЅРґС‹
            body = json.loads(response_frame.body.decode('utf8').strip('\0'))  # Р Р°СЃС€РёС„СЂРѕРІС‹РІР°РµРј РїСЂРёС€РµРґС€РµРµ СЃРѕРѕР±С‰РµРЅРёРµ
            self.logger.debug(f'РџСЂРёС€Р»Рё РґР°РЅРЅС‹Рµ WebSocket {cmd} - {headers} - {body}')
            if cmd == 'CONNECTED':  # РџРѕРґРєР»СЋС‡РµРЅРёРµ
                self.on_connected.trigger(headers, body)
            elif cmd == 'ERROR':  # РћС€РёР±РєР°
                self.on_error.trigger(headers, body)
            elif cmd == 'RECEIPT':
                self.on_receipt.trigger(headers, body)
            elif cmd == 'MESSAGE':  # РЎРѕРѕР±С‰РµРЅРёРµ (РґР°РЅРЅС‹Рµ РїРѕРґРїРёСЃРєРё)
                subscription_id = headers.get('subscription')  # РџС‹С‚Р°РµРјСЃСЏ РїРѕР»СѓС‡РёС‚СЊ СѓРЅРёРєР°Р»СЊРЅС‹Р№ РЅРѕРјРµСЂ РїРѕРґРїРёСЃРєРё
                if subscription_id is not None:  # Р•СЃР»Рё РїСЂРёС€Р»Рѕ СЃРѕРѕР±С‰РµРЅРёРµ РїРѕ РїРѕРґРїРёСЃРєРµ
                    headers.update(self.subscriptions[subscription_id])  # С‚Рѕ РІ Р·Р°РіРѕР»РѕРІРѕРє РґРѕР±Р°РІР»СЏРµРј РґР°РЅРЅС‹Рµ РїРѕРґРїРёСЃРєРё
                self.on_message.trigger(headers, body)
            elif cmd == 'REPLY':
                self.on_reply.trigger(headers, body)
            elif cmd == 'CLOSED':  # РћС‚РєР»СЋС‡РµРЅРёРµ
                self.on_closed.trigger(headers, body)

    # Р¤СѓРЅРєС†РёРё РєРѕРЅРІРµСЂС‚Р°С†РёРё

    @staticmethod
    def dataname_to_board_symbol(dataname) -> tuple[str | None, str]:
        """РљРѕРґ СЂРµР¶РёРјР° С‚РѕСЂРіРѕРІ Рё С‚РёРєРµСЂ РёР· РЅР°Р·РІР°РЅРёСЏ С‚РёРєРµСЂР°

        :param str dataname: РќР°Р·РІР°РЅРёРµ С‚РёРєРµСЂР°
        :return: РљРѕРґ СЂРµР¶РёРјР° С‚РѕСЂРіРѕРІ Рё С‚РёРєРµСЂ
        """
        symbol_parts = dataname.split('.')  # РџРѕ СЂР°Р·РґРµР»РёС‚РµР»СЋ РїС‹С‚Р°РµРјСЃСЏ СЂР°Р·Р±РёС‚СЊ С‚РёРєРµСЂ РЅР° С‡Р°СЃС‚Рё
        if len(symbol_parts) >= 2:  # Р•СЃР»Рё С‚РёРєРµСЂ Р·Р°РґР°РЅ РІ С„РѕСЂРјР°С‚Рµ <РљРѕРґ СЂРµР¶РёРјР° С‚РѕСЂРіРѕРІ>.<РљРѕРґ С‚РёРєРµСЂР°>
            board = symbol_parts[0]  # РљРѕРґ СЂРµР¶РёРјР° С‚РѕСЂРіРѕРІ
            symbol = '.'.join(symbol_parts[1:])  # РљРѕРґ С‚РёРєРµСЂР°
        else:  # Р•СЃР»Рё С‚РёРєРµСЂ Р·Р°РґР°РЅ Р±РµР· РєРѕРґР° СЂРµР¶РёРјР° С‚РѕСЂРіРѕРІ
            return None, dataname  # С‚Рѕ РєРѕРґ СЂС‹РЅРєР° РЅРµРёР·РІРµСЃС‚РµРЅ
        return board, symbol

    @staticmethod
    def board_symbol_to_dataname(board, symbol) -> str:
        """РќР°Р·РІР°РЅРёРµ С‚РёРєРµСЂР° РёР· РєРѕРґР° СЂРµР¶РёРјР° С‚РѕСЂРіРѕРІ Рё С‚РёРєРµСЂР°

        :param str board: РљРѕРґ СЂРµР¶РёРјР° С‚РѕСЂРіРѕРІ
        :param str symbol: РўРёРєРµСЂ
        :return: РќР°Р·РІР°РЅРёРµ С‚РёРєРµСЂР°
        """
        return f'{board}.{symbol}'

    def get_market_engine(self, board: str) -> tuple[str | None, str | None, str | None]:
        """Р С‹РЅРѕРє Рё С‚РѕСЂРіРѕРІР°СЏ РїР»РѕС‰Р°РґРєР° РёР· СЂРµР¶РёРјР° С‚РѕСЂРіРѕРІ

        :param str board: Р РµР¶РёРј С‚РѕСЂРіРѕРІ
        :return: Р С‹РЅРѕРє, С‚РѕСЂРіРѕРІР°СЏ РїР»РѕС‰Р°РґРєР°
        """
        board_row = self.boards_dict.get(board)  # РЎС‚СЂРѕРєР° СЂРµР¶РёРјР° С‚РѕСЂРіРѕРІ
        if board_row is None:  # Р•СЃР»Рё РЅРµ РЅР°Р№РґРµРЅР°
            self.logger.error(f'РќРµРёР·РІРµСЃС‚РЅС‹Р№ СЂС‹РЅРѕРє Рё С‚РѕСЂРіРѕРІР°СЏ РїР»РѕС‰Р°РґРєР° РґР»СЏ СЂРµР¶РёРјР° С‚РѕСЂРіРѕРІ {board}')
            return None, None, None  # С‚Рѕ Рё СЂС‹РЅРєРё СЃ С‚РѕСЂРіРѕРІС‹РјРё РїР»РѕС‰Р°РґРєР°РјРё РЅР°Р№С‚Рё РЅРµ СѓРґР°СЃС‚СЃСЏ. Р’С‹С…РѕРґРёРј, РґР°Р»СЊС€Рµ РЅРµ РїСЂРѕРґРѕР»Р¶Р°РµРј
        market_row = self.markets_dict.get(board_row['market_id'])  # РЎС‚СЂРѕРєР° СЂС‹РЅРєР° (РґРѕР»Р¶РЅР° Р±С‹С‚СЊ)
        return market_row['market_name'], market_row['marketplace'], market_row['trade_engine_name']  # РќР°РїСЂРёРјРµСЂ: shares, MXSE, stock

    @staticmethod
    def timeframe_to_moex_timeframe(tf: str) -> int:
        """РџРµСЂРµРІРѕРґ РІСЂРµРјРµРЅРЅРћРіРѕ РёРЅС‚РµСЂРІР°Р»Р° РІРѕ РІСЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рё (REST)

        :param str tf: Р’СЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» https://ru.wikipedia.org/wiki/РўР°Р№РјС„СЂРµР№Рј
        :return: Р’СЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рё
        """
        tf_map = {'M1': 1, 'M10': 10, 'M60': 60, 'D1': 24, 'W1': 7, 'MN1': 31, 'MN3': 4}  # РЎРїСЂР°РІРѕС‡РЅРёРє РІСЂРµРјРµРЅРЅР«С… РёРЅС‚РµСЂРІР°Р»РѕРІ
        if tf in tf_map:  # Р•СЃР»Рё РІСЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» РµСЃС‚СЊ РІ СЃРїСЂР°РІРѕС‡РЅРёРєРµ
            return tf_map[tf]  # С‚Рѕ РІРѕР·РІСЂР°С‰Р°РµРј РІСЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» Р¤РёРЅР°РјР°
        raise NotImplementedError(f'Р’СЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» {tf} РЅРµ РїРѕРґРґРµСЂР¶РёРІР°РµС‚СЃСЏ')  # РЎ РѕСЃС‚Р°Р»СЊРЅС‹РјРё РІСЂРµРјРµРЅРЅР«РјРё РёРЅС‚РµСЂРІР°Р»Р°РјРё РЅРµ СЂР°Р±РѕС‚Р°РµРј

    @staticmethod
    def timeframe_to_moex_ws_timeframe(tf: str) -> str:
        """РџРµСЂРµРІРѕРґ РІСЂРµРјРµРЅРЅРћРіРѕ РёРЅС‚РµСЂРІР°Р»Р° РІРѕ РІСЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рё (WebSockets)

        :param str tf: Р’СЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» https://ru.wikipedia.org/wiki/РўР°Р№РјС„СЂРµР№Рј
        :return: Р’СЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рё (WebSockets)
        """
        tf_map = {'M1': 'M1', 'M10': 'M10', 'M60': 'H1', 'D1': 'D1', 'W1': 'W1', 'MN1': 'm1', 'MN3': 'Q1'}  # РЎРїСЂР°РІРѕС‡РЅРёРє РІСЂРµРјРµРЅРЅР«С… РёРЅС‚РµСЂРІР°Р»РѕРІ
        if tf in tf_map:  # Р•СЃР»Рё РІСЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» РµСЃС‚СЊ РІ СЃРїСЂР°РІРѕС‡РЅРёРєРµ
            return tf_map[tf]  # С‚Рѕ РІРѕР·РІСЂР°С‰Р°РµРј РІСЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» Р¤РёРЅР°РјР°
        raise NotImplementedError(f'Р’СЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» {tf} РЅРµ РїРѕРґРґРµСЂР¶РёРІР°РµС‚СЃСЏ')  # РЎ РѕСЃС‚Р°Р»СЊРЅС‹РјРё РІСЂРµРјРµРЅРЅР«РјРё РёРЅС‚РµСЂРІР°Р»Р°РјРё РЅРµ СЂР°Р±РѕС‚Р°РµРј

    @staticmethod
    def moex_timeframe_to_timeframe(moex_tf) -> str:
        """РџРµСЂРµРІРѕРґ РІСЂРµРјРµРЅРЅРћРіРѕ РёРЅС‚РµСЂРІР°Р»Р° РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рё (REST) РІРѕ РІСЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р»

        :param int moex_tf: Р’СЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рё (REST)
        :return: Р’СЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» https://ru.wikipedia.org/wiki/РўР°Р№РјС„СЂРµР№Рј
        """
        tf_map = {1: 'M1', 10: 'M10', 60: 'M60', 24: 'D1', 7: 'W1', 31: 'MN1', 4: 'MN3'}  # РЎРїСЂР°РІРѕС‡РЅРёРє РІСЂРµРјРµРЅРЅР«С… РёРЅС‚РµСЂРІР°Р»РѕРІ РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рё
        if moex_tf in tf_map:  # Р•СЃР»Рё РІСЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рё РµСЃС‚СЊ РІ СЃРїСЂР°РІРѕС‡РЅРёРєРµ
            return tf_map[moex_tf]  # С‚Рѕ РІРѕР·РІСЂР°С‰Р°РµРј РІСЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р»
        raise NotImplementedError(f'Р’СЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рё {moex_tf} РЅРµ РїРѕРґРґРµСЂР¶РёРІР°РµС‚СЃСЏ')  # РЎ РѕСЃС‚Р°Р»СЊРЅС‹РјРё РІСЂРµРјРµРЅРЅР«РјРё РёРЅС‚РµСЂРІР°Р»Р°РјРё РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рё РЅРµ СЂР°Р±РѕС‚Р°РµРј

    @staticmethod
    def moex_ws_timeframe_to_timeframe(moex_tf) -> str:
        """РџРµСЂРµРІРѕРґ РІСЂРµРјРµРЅРЅРћРіРѕ РёРЅС‚РµСЂРІР°Р»Р° РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рё (WebSockets) РІРѕ РІСЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р»

        :param str moex_tf: Р’СЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рё (WebSockets)
        :return: Р’СЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» https://ru.wikipedia.org/wiki/РўР°Р№РјС„СЂРµР№Рј
        """
        tf_map = {'M1': 'M1', 'M10': 'M10', 'H1': 'M60', 'D1': 'D1', 'W1': 'W1', 'm1': 'MN1', 'Q1': 'MN3'}  # РЎРїСЂР°РІРѕС‡РЅРёРє РІСЂРµРјРµРЅРЅР«С… РёРЅС‚РµСЂРІР°Р»РѕРІ РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рё
        if moex_tf in tf_map:  # Р•СЃР»Рё РІСЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рё РµСЃС‚СЊ РІ СЃРїСЂР°РІРѕС‡РЅРёРєРµ
            return tf_map[moex_tf]  # С‚Рѕ РІРѕР·РІСЂР°С‰Р°РµРј РІСЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р»
        raise NotImplementedError(f'Р’СЂРµРјРµРЅРЅРѕР№ РёРЅС‚РµСЂРІР°Р» РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рё {moex_tf} РЅРµ РїРѕРґРґРµСЂР¶РёРІР°РµС‚СЃСЏ')  # РЎ РѕСЃС‚Р°Р»СЊРЅС‹РјРё РІСЂРµРјРµРЅРЅР«РјРё РёРЅС‚РµСЂРІР°Р»Р°РјРё РњРѕСЃРєРѕРІСЃРєРѕР№ Р‘РёСЂР¶Рё РЅРµ СЂР°Р±РѕС‚Р°РµРј

    def get_long_token_from_keyring(self, service: str, username: str) -> str | None:
        """РџРѕР»СѓС‡РµРЅРёРµ С‚РѕРєРµРЅР° РёР· СЃРёСЃС‚РµРјРЅРѕРіРѕ С…СЂР°РЅРёР»РёС‰Р° keyring РїРѕ С‡Р°СЃС‚СЏРј"""
        try:
            index = 0  # РќРѕРјРµСЂ С‡Р°СЃС‚Рё С‚РѕРєРµРЅР°
            token_parts = []  # Р§Р°СЃС‚Рё С‚РѕРєРµРЅР°
            while True:  # РџРѕРєР° РµСЃС‚СЊ С‡Р°СЃС‚Рё С‚РѕРєРµРЅР°
                token_part = keyring.get_password(service, f'{username}{index}')  # РџРѕР»СѓС‡Р°РµРј С‡Р°СЃС‚СЊ С‚РѕРєРµРЅР°
                if token_part is None:  # Р•СЃР»Рё С‡Р°СЃС‚Рё С‚РѕРєРµРЅР° РЅРµС‚
                    break  # С‚Рѕ РІС‹С…РѕРґРёРј, РґР°Р»СЊС€Рµ РЅРµ РїСЂРѕРґРѕР»Р¶Р°РµРј
                token_parts.append(token_part)  # Р”РѕР±Р°РІР»СЏРµРј С‡Р°СЃС‚СЊ С‚РѕРєРµРЅР°
                index += 1  # РџРµСЂРµС…РѕРґРёРј Рє СЃР»РµРґСѓСЋС‰РµР№ С‡Р°СЃС‚Рё С‚РѕРєРµРЅР°
            if not token_parts:  # Р•СЃР»Рё С‚РѕРєРµРЅ РЅРµ РЅР°Р№РґРµРЅ
                # self.logger.error(f'РўРѕРєРµРЅ РЅРµ РЅР°Р№РґРµРЅ РІ СЃРёСЃС‚РµРјРЅРѕРј С…СЂР°РЅРёР»РёС‰Рµ. Р’С‹Р·РѕРІРёС‚Рµ mp_provider = MOEXPy("<РўРѕРєРµРЅ>")')
                return None
            token = ''.join(token_parts)  # РЎРѕР±РёСЂР°РµРј С‚РѕРєРµРЅ РёР· С‡Р°СЃС‚РµР№
            self.logger.debug('РўРѕРєРµРЅ СѓСЃРїРµС€РЅРѕ Р·Р°РіСЂСѓР¶РµРЅ РёР· СЃРёСЃС‚РµРјРЅРѕРіРѕ С…СЂР°РЅРёР»РёС‰Р°')
            return token
        except keyring.errors.KeyringError as e:
            self.logger.fatal(f'РћС€РёР±РєР° РґРѕСЃС‚СѓРїР° Рє СЃРёСЃС‚РµРјРЅРѕРјСѓ С…СЂР°РЅРёР»РёС‰Сѓ: {e}')
        except Exception as e:
            self.logger.fatal(f'РћС€РёР±РєР° РїСЂРё Р·Р°РіСЂСѓР·РєРµ С‚РѕРєРµРЅР°: {e}')

    def set_long_token_to_keyring(self, service: str, username: str, token: str, password_split_size: int = 500) -> None:
        """РЈСЃС‚Р°РЅРѕРІРєР° С‚РѕРєРµРЅР° РІ СЃРёСЃС‚РµРјРЅРѕРµ С…СЂР°РЅРёР»РёС‰Рµ keyring РїРѕ С‡Р°СЃС‚СЏРј"""
        try:
            self.clear_long_token_from_keyring(service, username)  # РћС‡РёС‰Р°РµРј РїСЂРµРґС‹РґСѓС‰РёРµ С‡Р°СЃС‚Рё С‚РѕРєРµРЅР°
            token_parts = [token[i:i + password_split_size] for i in range(0, len(token), password_split_size)]  # Р Р°Р·Р±РёРІР°РµРј С‚РѕРєРµРЅ РЅР° С‡Р°СЃС‚Рё Р·Р°РґР°РЅРЅРѕРіРѕ СЂР°Р·РјРµСЂР°
            for index, token_part in enumerate(token_parts):  # РџСЂРѕР±РµРіР°РµРјСЃСЏ РїРѕ С‡Р°СЃС‚СЏРј С‚РѕРєРµРЅР°
                keyring.set_password(service, f'{username}{index}', token_part)  # РЎРѕС…СЂР°РЅСЏРµРј С‡Р°СЃС‚СЊ С‚РѕРєРµРЅР°
            self.logger.debug(f'Р§Р°СЃС‚РµР№ СЃРѕС…СЂР°РЅРµРЅРЅРѕРіРѕ С‚РѕРєРµРЅР° РІ С…СЂР°РЅРёР»РёС‰Рµ: {len(token_parts)}')
        except keyring.errors.KeyringError as e:
            self.logger.fatal(f'РћС€РёР±РєР° СЃРѕС…СЂР°РЅРµРЅРёСЏ РІ СЃРёСЃС‚РµРјРЅРѕРµ С…СЂР°РЅРёР»РёС‰Рµ: {e}')
        except Exception as e:
            self.logger.fatal(f'РћС€РёР±РєР° РїСЂРё СЃРѕС…СЂР°РЅРµРЅРёРё С‚РѕРєРµРЅР°: {e}')

    def clear_long_token_from_keyring(self, service: str, username: str) -> None:
        """РЈРґР°Р»РµРЅРёРµ РІСЃРµС… С‡Р°СЃС‚РµР№ С‚РѕРєРµРЅР° РёР· СЃРёСЃС‚РµРјРЅРѕРіРѕ С…СЂР°РЅРёР»РёС‰Р° keyring"""
        try:
            index = 0  # РќРѕРјРµСЂ С‡Р°СЃС‚Рё С‚РѕРєРµРЅР°
            while True:  # РџРѕРєР° РµСЃС‚СЊ С‡Р°СЃС‚Рё С‚РѕРєРµРЅР°
                if keyring.get_password(service, f'{username}{index}') is None:  # Р•СЃР»Рё С‡Р°СЃС‚Рё С‚РѕРєРµРЅР° РЅРµС‚
                    break  # С‚Рѕ РІС‹С…РѕРґРёРј, РґР°Р»СЊС€Рµ РЅРµ РїСЂРѕРґРѕР»Р¶Р°РµРј
                keyring.delete_password(service, f'{username}{index}')  # РЈРґР°Р»СЏРµРј С‡Р°СЃС‚СЊ С‚РѕРєРµРЅР°
                index += 1  # РџРµСЂРµС…РѕРґРёРј Рє СЃР»РµРґСѓСЋС‰РµР№ С‡Р°СЃС‚Рё С‚РѕРєРµРЅР°
        except keyring.errors.KeyringError as e:
            self.logger.fatal(f'РћС€РёР±РєР° РґРѕСЃС‚СѓРїР° Рє СЃРёСЃС‚РµРјРЅРѕРјСѓ С…СЂР°РЅРёР»РёС‰Сѓ: {e}')


    def get_tradestats(self, ticker, dt_from, dt_till, board='TQBR'):
        """Super Candles: агрегированная статистика сделок (Algopack)

        :param str ticker: Тикер акции
        :param date dt_from: Дата начала
        :param date dt_till: Дата окончания
        :param str board: Режим торгов (TQBR для акций)
        :return: dict с ключами 'data', 'data.cursor', 'data.dates'
        """
        from datetime import timedelta
        from requests import get
        from json import loads

        # Определяем тип рынка по board
        market_map = {'TQBR': 'eq', 'TQTF': 'eq', 'RFUD': 'fo', 'SPBFUT': 'fo'}
        market_code = market_map.get(board, 'eq')

        url = f'{self.api_server}/datashop/algopack/{market_code}/tradestats/{ticker}.json'
        all_data = None
        cursor = 0

        while True:
            params = {
                'from': dt_from.strftime('%Y-%m-%d'),
                'till': dt_till.strftime('%Y-%m-%d'),
                'start': cursor
            }
            response = get(url, params=params, headers=self.headers)
            content = loads(response.content.decode('utf-8'))

            # Поддержка нового формата (metadata + columns + data) для срочных фьючерсов
            if isinstance(content['data']['data'], dict) and 'data' in content['data']['data']:
                rows = content['data']['data']['data']
            else:
                rows = content['data']['data']
            total = content['data.cursor']['data'][0][1] if content['data.cursor']['data'] else 0

            if all_data is None:
                all_data = content
            else:
                all_data['data']['data'].extend(rows)

            cursor += len(rows)
            if cursor >= total or len(rows) == 0:
                break

        return all_data


class Event:


    """РЎРѕР±С‹С‚РёРµ СЃ РїРѕРґРїРёСЃРєРѕР№ / РѕС‚РјРµРЅРѕР№ РїРѕРґРїРёСЃРєРё"""
    def __init__(self):
        self._callbacks: set[Any] = set()  # РР·Р±РµРіР°РµРј РґСѓР±Р»РёРєР°С‚РѕРІ С„СѓРЅРєС†РёР№ РїСЂРё РїРѕРјРѕС‰Рё set

    def subscribe(self, callback) -> None:
        """РџРѕРґРїРёСЃР°С‚СЊСЃСЏ РЅР° СЃРѕР±С‹С‚РёРµ"""
        self._callbacks.add(callback)  # Р”РѕР±Р°РІР»СЏРµРј С„СѓРЅРєС†РёСЋ РІ СЃРїРёСЃРѕРє

    def unsubscribe(self, callback) -> None:
        """РћС‚РїРёСЃР°С‚СЊСЃСЏ РѕС‚ СЃРѕР±С‹С‚РёСЏ"""
        self._callbacks.discard(callback)  # РЈРґР°Р»СЏРµРј С„СѓРЅРєС†РёСЋ РёР· СЃРїРёСЃРєР°. Р•СЃР»Рё С„СѓРЅРєС†РёРё РЅРµС‚ РІ СЃРїРёСЃРєРµ, С‚Рѕ РЅРµ Р±СѓРґРµС‚ РѕС€РёР±РєРё

    def trigger(self, *args, **kwargs) -> None:
        """Р’С‹Р·РІР°С‚СЊ СЃРѕР±С‹С‚РёРµ"""
        for callback in list(self._callbacks):  # РџСЂРѕР±РµРіР°РµРјСЃСЏ РїРѕ РєРѕРїРёРё СЃРїРёСЃРєР°, С‡С‚РѕР±С‹ РёР·Р±РµР¶Р°С‚СЊ РёСЃРєР»СЋС‡РµРЅРёСЏ РїСЂРё СѓРґР°Р»РµРЅРёРё
            callback(*args, **kwargs)  # Р’С‹Р·С‹РІР°РµРј С„СѓРЅРєС†РёСЋ

