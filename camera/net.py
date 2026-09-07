"""One keep-alive HTTP session shared by every module that talks to the cloud.

On the weak Wi-Fi link at the apiary each fresh TLS handshake is several
lossy round-trips; a cycle used to open a brand-new connection for every
single request. Reusing one session keeps the beeSys and Blynk connections
open across the cycle.
"""
import requests

session = requests.Session()
