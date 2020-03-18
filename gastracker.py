from bs4 import BeautifulSoup
import requests
from requests_html import HTMLSession
import re
from PIL import Image
import pytesseract
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import pushnotification
import sys

scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']

credentials = ServiceAccountCredentials.from_json_keyfile_name('Gas tracker.json', scope)

gc = gspread.authorize(credentials)  # Authentification


def get_html(url):  # gets html from url given
    html = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    content = html.content
    return BeautifulSoup(content, "html.parser")


def get_html_with_js(url):
    session = HTMLSession()
    response = session.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    response.html.render(sleep=2, keep_page=True)
    return BeautifulSoup(response.html.html, "html.parser")


def crop_and_resize(img, y1):  # crops the image containing fuel price info into boxes that contain only the prices and enlarges the resulting image in order to aid OCR
    size = 680, 160
    cropped_img = img.crop((245, y1, 330, y1 + 20))  # second and last parameters signify upper and lower bound
    return cropped_img.resize(size, Image.ANTIALIAS)


def get_price(gas_img): #does the OCR
    price = pytesseract.image_to_string(Image.open(gas_img), lang='eng', config='--psm 6')
    return re.sub('[^0-9\.]', '', price).rstrip("0")


def extract_petrom_img(string):  # extracts the image containing pricing info
    url = re.findall(r'(https?://[a-zA-Z0-9_./]+)', string)
    return Image.open(requests.get(url[0], stream=True).raw).convert('L')  # open image and convert to grayscale


def get_time():
    time = datetime.datetime.now()  # current time
    return time.strftime("%d.%m.%Y")


def is_different(row, std_diesel, prem_diesel, std_gas, prem_gas):
    if row[1] == std_diesel and row[2] == prem_diesel and row[3] == std_gas and row[4] == prem_gas:
        return False
    else:
        return True


try:
    input_arg = sys.argv[1]
except IndexError:
    input_arg = ""

remote_call = False
if input_arg == "remote":
    remote_call = True

print(remote_call)
crop_offset = 35         # used to extract useful portion of image

oil_soup = get_html('https://oilprice.com')
oil_prices = oil_soup.findAll("td", {"class": "value"})


oil_price_WTI_content = str(oil_prices[0].contents)
oil_WTI = re.findall("\d+\.\d+", oil_price_WTI_content)
oil_WTI_float = float(oil_WTI[0])
print(oil_WTI_float)  # WTI price

oil_price_Brent_content = str(oil_prices[1].contents)
oil_Brent = re.findall("\d+\.\d+", oil_price_Brent_content)
oil_Brent_float = float(oil_Brent[0])
print(oil_Brent_float)  # Brent price


petrom_URL = "https://app.wigeogis.com/kunden/omvpetrom/map.php?BRAND=PETROM&CTRISO=ROU&X=undefined&Y=" \
             "undefined&ADRTEXT=undefined&DISPATCH=1&STATIONID=RO.1542.8&LNG=RO&LNG=RO&ADRTEXT=undefined&DISPATCH=" \
             "1&STATIONID=RO.1542.8&X=undefined&Y=undefined"
petrom_soup = get_html_with_js(petrom_URL)
petrom_prices = petrom_soup.find("img", {"id": "priceImg"})  # finds the img tag which has the price info

petrom_prices_img = extract_petrom_img(str(petrom_prices))

diesel_std_crop_start = 38
diesel_std_crop_img_resized = crop_and_resize(petrom_prices_img, diesel_std_crop_start)
diesel_std_crop_img_resized.save("dieselstdcrop.png", "PNG")
diesel_std_price = get_price("dieselstdcrop.png")
print(diesel_std_price)

diesel_prem_crop_start = 64
diesel_prem_crop_img_resized = crop_and_resize(petrom_prices_img, diesel_prem_crop_start)
diesel_prem_crop_img_resized.save("dieselpremcrop.png", "PNG")
diesel_prem_price = get_price("dieselpremcrop.png")
print(diesel_prem_price)


gas_std_crop_start = 113
gas_std_crop_img_resized = crop_and_resize(petrom_prices_img, gas_std_crop_start)
gas_std_crop_img_resized.save("gasstdcrop.png", "PNG")
gas_std_price = get_price("gasstdcrop.png")
print(gas_std_price)

gas_prem_crop_start = 139
gas_prem_crop_img_resized = crop_and_resize(petrom_prices_img, gas_prem_crop_start)
gas_prem_crop_img_resized.save("gaspremcrop.png", "PNG")
gas_prem_price = get_price("gaspremcrop.png")
print(gas_prem_price)


formatted_time = get_time()

new_row_data = formatted_time, diesel_std_price, diesel_prem_price, gas_std_price, gas_prem_price, oil_WTI_float, \
               oil_Brent_float  # data to add to sheet

sheet_ID_file = open("sheetID.txt")
sheet_ID = sheet_ID_file.read()


sheet = gc.open_by_key(sheet_ID).sheet1  # opens the sheet to which we are going to append

list_of_prices = sheet.get_all_values()  # get the updated sheet data
nr_of_rows = len(list_of_prices)

last_row = sheet.row_values(nr_of_rows)


pushnotif_title = "Diesel: " + str(diesel_std_price) + ", Gas: " + str(gas_std_price) + ", WTI: " + str(oil_WTI_float) \
                  + ", Brent: " + str(oil_Brent_float)
current_hour = datetime.datetime.now().hour


if is_different(last_row,diesel_std_price,diesel_prem_price,gas_std_price,gas_prem_price) and not remote_call:
    sheet.append_row(new_row_data, value_input_option='USER_ENTERED')  # appends new data
    pushnotification.push_to_iOS("Price change: " + pushnotif_title, "Price change", "pb_key.txt")
elif formatted_time != last_row[0] and current_hour == 21 and not remote_call:
    sheet.append_row(new_row_data, value_input_option='USER_ENTERED')  # appends data if no price change happened today
    pushnotification.push_to_iOS("Daily Update: " + pushnotif_title, "Daily Update", "pb_key.txt")
elif remote_call:
    pushnotification.push_to_iOS("Current prices: " + pushnotif_title, "Remote call", "pb_key.txt")

# # print(list_of_prices)



