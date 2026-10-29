# Download the helper library from https://www.twilio.com/docs/python/install
import os
from twilio.rest import Client

# Set environment variables for your credentials
# Read more at http://twil.io/secure

account_sid = "<TWILIO_ACCOUNT_SID>"
auth_token = "<TWILIO_AUTH_TOKEN>"
client = Client(account_sid, auth_token)

call = client.calls.create(
  url="http://demo.twilio.com/docs/voice.xml",
  to="<ACERTING_PHONE_NUMBER>",
  from_="<TWILIO_PHONE_NUMBER>"
)

print(call.sid)