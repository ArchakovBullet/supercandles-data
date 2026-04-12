# ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ (ТОКЕНЫ)

Все токены и пароли хранятся в переменных окружения Windows (постоянно).

## Установленные переменные:

| Переменная | Назначение | Статус |
|------------|------------|--------|
| MOEX_TOKEN | Algopack (Московская биржа) | ✅ Установлен |
| TINVEST_TOKEN | Т-Инвест API | ✅ Установлен |
| ALOR_TOKEN | АЛОР API | ✅ Установлен |

## Как проверить:

 + "" + "" + "powershell" + 
echo eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJaVHA2Tjg1ekE4YTBFVDZ5SFBTajJ2V0ZldzNOc2xiSVR2bnVaYWlSNS1NIn0.eyJleHAiOjE4MDY5MDU2MjgsImlhdCI6MTc3NTgwMTY2OCwiYXV0aF90aW1lIjoxNzc1ODAxNjI4LCJqdGkiOiJjMDcwNmIyZS05NjA1LTQxMDEtYTJjOS0xMWMzNjBlOWE2N2QiLCJpc3MiOiJodHRwczovL3NzbzIubW9leC5jb20vYXV0aC9yZWFsbXMvY3JhbWwiLCJhdWQiOlsiYWNjb3VudCIsImlzcyJdLCJzdWIiOiJmOjBiYTZhOGYwLWMzOGEtNDlkNi1iYTBlLTg1NmYxZmU0YmY3ZTphNGU5OGMzZi01ZjhmLTQ2NTQtYTgzZS00Y2RlZWIwYjFiYTMiLCJ0eXAiOiJCZWFyZXIiLCJhenAiOiJpc3MiLCJzaWQiOiIxNDA0ZDZiMy0xOTFiLTRhODktODIyMS04MmVhMTZlYTlhMDciLCJhY3IiOiIxIiwiYWxsb3dlZC1vcmlnaW5zIjpbIi8qIl0sInJlYWxtX2FjY2VzcyI6eyJyb2xlcyI6WyJvZmZsaW5lX2FjY2VzcyIsInVtYV9hdXRob3JpemF0aW9uIl19LCJyZXNvdXJjZV9hY2Nlc3MiOnsiYWNjb3VudCI6eyJyb2xlcyI6WyJtYW5hZ2UtYWNjb3VudCIsInZpZXctcHJvZmlsZSJdfX0sInNjb3BlIjoib3BlbmlkIGlzc19hbGdvcGFjayBwcm9maWxlIG9mZmxpbmVfYWNjZXNzIGVtYWlsIGJhY2t3YXJkc19jb21wYXRpYmxlIiwiZW1haWxfdmVyaWZpZWQiOmZhbHNlLCJpc3NfcGVybWlzc2lvbnMiOiIwIiwibmFtZSI6ItCU0LXQvdC40YEg0JDRgNGH0LDQutC-0LIiLCJwcmVmZXJyZWRfdXNlcm5hbWUiOiJhNGU5OGMzZi01ZjhmLTQ2NTQtYTgzZS00Y2RlZWIwYjFiYTMiLCJnaXZlbl9uYW1lIjoi0JTQtdC90LjRgSIsInNlc3Npb25fc3RhdGUiOiIxNDA0ZDZiMy0xOTFiLTRhODktODIyMS04MmVhMTZlYTlhMDciLCJmYW1pbHlfbmFtZSI6ItCQ0YDRh9Cw0LrQvtCyIn0.IXT-LzVqNmSxlaytcykft_5LyEHu5TEJWL6po9t-z9KQEEVwy53RxZAnnJmblyM_QtOmNrepGoI9hsbCMDvvezuziYYEKYIn-w4b7o4Gec7FChUfFittUGuerxG7bdy4EPDPQMOKT2jNkC1rApL9hG6FSHKuzbBV5w-GFnGo2j7SADsxc9aGuScg5FGarJ5WlOOdQ4mGB_vhxOBei6IOZ3IXnf5a1GWN_q2coIQKdZcWk-DD9vJbuGHXdFtVM8Sayaz2QKj9UvQ39nldBcxAXZqlNL2PF2aQjYwg-EsdyE9eaJIL1I7mOIKUu3fjqC9j7EsfogwJEiEx8l2xFhMVOg.Substring(0, 20) + "..."
echo t._ebFOMiqvdNb67cICoepA_VlHKseLgs6wIj9cvPnnKPYSz0lq-4_dK1GaBQ_zFNFUzXw5ExTiH-sIhSDF-ztFg.Substring(0, 20) + "..."
echo 3f75e20c-75e2-4105-8ec7-e03a2a51bd71
 + "" + "" + "" + 

## Как использовать в коде:

 + "" + "" + "python" + 
import os

moex_token = os.getenv('MOEX_TOKEN')
tinvest_token = os.getenv('TINVEST_TOKEN')
alor_token = os.getenv('ALOR_TOKEN')
 + "" + "" + "" + 

**Дата настройки:** 12.04.2026
