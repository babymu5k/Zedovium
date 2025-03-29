import requests, hmac, hashlib


t = requests.post("http://127.0.0.1:4024/transaction/create",json={
    "sender":"ZED-alien-ladybug-glow-garden-cecd",
    "recipient":"ZED-free-pearl-autumn-image-bd89",
    "amount": "10223",
    "seed": "17bfca614286a7497b049d6db246844c"
})

print(t.content.decode())