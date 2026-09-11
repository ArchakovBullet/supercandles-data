#!/bin/bash
# Восстановление сертификата НУЦ Минцифры для доступа к MOEX
CERT_URL="https://gu-st.ru/content/Other/doc/russiantrustedca.pem"
CERT_PATH="/tmp/russian_trusted_ca.pem"
SYS_PATH="/usr/local/share/ca-certificates/russian_trusted_ca.crt"

# Системный trust store
if [ ! -f "$SYS_PATH" ]; then
    wget -q "$CERT_URL" -O "$CERT_PATH"
    cp "$CERT_PATH" "$SYS_PATH"
    update-ca-certificates
    echo "✅ Системный сертификат установлен"
else
    echo "✅ Системный сертификат уже есть"
fi

# certifi (Python)
CERTIFI=$(/root/finlab/venv/bin/python -c "import certifi; print(certifi.where())")
if ! grep -q "Russian Trusted" "$CERTIFI"; then
    cat "$SYS_PATH" >> "$CERTIFI"
    echo "✅ certifi обновлён"
else
    echo "✅ certifi уже содержит сертификат"
fi

# Проверка
echo "--- Проверка ---"
curl -sS -o /dev/null -w "iss: %{http_code}\n" https://iss.moex.com/iss/engines/stock/markets/shares/securities.json --max-time 10
/root/finlab/venv/bin/python -c "import requests; print('python iss:', requests.get('https://iss.moex.com/iss/engines/stock/markets/shares/securities.json', timeout=10).status_code)"
