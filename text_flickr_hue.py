# text_flickr_hue.py
# For changing Hue lights based on Flickr image from SMS keyword
# Created by Robert Bennett (robertbe@uw.edu) for UW HCDE's Internet of Light DRG

#IMPORTS
import time
import json
import requests
import re
import sys
from datetime import datetime
import colorgram # Install: pip3 install colorgram.py
from rgbxy import Converter # Install (manual): https://github.com/benknight/hue-python-rgb-converter
import TextMagic # Install: pip3 install git+https://github.com/textmagic/textmagic-rest-python-v2.git@v2.0.1067
from TextMagic.rest import ApiException

#CONSTANTS
TMCREDSFILE = 'textmagic_creds.txt'
FRCREDSFILE = 'flickr_creds.txt'
HUBIP = '172.28.219.179' # master
HUBUSER = 'rARKEpLebwXuW01cNVvQbnDEkd2bd56Nj-hpTETB' # master
BASEAPIURL = 'http://' + HUBIP + '/api/' + HUBUSER + '/'
NUMOFCOLORS = 3  # The number of colors to sample from the photo (needs to equal max number of rows on a floor)

# light numbers (NW to SE)
FIRSTLIGHTS = (22, 15, 10,\
               21,  7, 23,\
               16, 14, 11)

SECONDLIGHTS = (18, 20, 12,\
                25, 26,  5,\
                 8, 19, 13,\
                24,  9, 17)

ALLLIGHTS = FIRSTLIGHTS + SECONDLIGHTS

#HELPERS
# establishApiConnection
# in: None (Uses CREDSFILE constant)
# out: A TextMagic Api connection
def establishApiConnection():
    tmConfig = TextMagic.Configuration()

    # Get creds from file
    tmCredsFile = open(TMCREDSFILE, 'r')
    tmConfig.username = tmCredsFile.readline().strip('\n')
    tmConfig.password = tmCredsFile.readline().strip('\n')
    tmCredsFile.close()

    return(TextMagic.TextMagicApi(TextMagic.ApiClient(tmConfig)))   # Create API session using creds


# updateMessageQueue
# in: The existing message queue and api session
# out: The inputted message queue with new messages added to the end
def updateMessageQueue(messQue, apiSess):
    results = apiSess.get_all_inbound_messages(page = 1,\
                                               limit = 10,\
                                               order_by = 'messageTime',\
                                               direction = 'desc')  # Gets up to 10 messages to add per query (in order received)
    
    for message in results.resources:                       # For each message:
        messQue.append(message.text)                            # Add text onto the queue
        apiSess.delete_inbound_message(id = message.id)         # Delete the message from MagicText

    return(messQue)


# cleanMessage
# in: An uncleaned message string
# out: A lowercase version of the inputted message, cleared of non-alphanumeric characters
def cleanMessage(originalMessage):
    return re.sub('[^a-zA-Z0-9]', '', originalMessage).lower()


# messageToFlickrImage
# in: A search term to send to Flickr
# out: A image returned from the search term ('photo.jpg')
def messageToFlickrImage(searchTerm, saveFile):
    # get creds from file
    frCredsFile = open(FRCREDSFILE, 'r')
    frKey = frCredsFile.readline().strip('\n')
    frSecret = frCredsFile.readline().strip('\n')
    frCredsFile.close()

    # get a single-photo metadata list (first matching photo only) of the photos on Flickr matching the search term
    singlePhotoList = requests.get('https://api.flickr.com/services/rest/',\
                                   params={'api_key': frKey,\
                                           'method': 'flickr.photos.search',\
                                           'format': 'json',\
                                           'nojsoncallback': '1',\
                                           'per_page': '1',\
                                           'page': '1',\
                                           'sort': 'relevance',\
                                           'text': searchTerm})
    
    photoId = singlePhotoList.json()['photos']['photo'][0]['id']

    # get URL of photo to download
    photoDetails = requests.get('https://api.flickr.com/services/rest/',\
                                params={'api_key': frKey,\
                                        'method': 'flickr.photos.getSizes',\
                                        'format': 'json',\
                                        'nojsoncallback': '1',\
                                        'photo_id': photoId})

    photoURL = photoDetails.json()['sizes']['size'][7]['source']

    # download photo from Flickr to local
    photoData = requests.get(photoURL, stream=True)
    photoFile = open(saveFile, 'wb')
    for chunk in photoData.iter_content(chunk_size=128):
        if chunk:
                photoFile.write(chunk)


# outputColorsFromPhoto
# in: A photo to extract colors from
# out: A colorsDict containing extracted colors for each light
def outputColorsFromPhoto(photo):
    colorsDict = {}
    photoColors = colorgram.extract(photo, NUMOFCOLORS)

    colorsDict = mapColorsToDict(colorsDict, photoColors, FIRSTLIGHTS, 2)
    colorsDict = mapColorsToDict(colorsDict, photoColors, SECONDLIGHTS, 2)

    return colorsDict

# mapColorsToDict
# in: The colorsDict, array of lights, and number of rows in array for a floor of lights
# out:  The colorDict with lights added for each color on floor
def mapColorsToDict(colorsDict, photoColors, lightsArray, lastRowNum):
    colorConverter = Converter()
    rowNum = 0

    for light in lightsArray:
        colorsDict[light] = colorConverter.rgb_to_xy(photoColors[rowNum].rgb[0],\
                                                     photoColors[rowNum].rgb[1],\
                                                     photoColors[rowNum].rgb[2])
        if rowNum == lastRowNum:
            rowNum = 0
        else:
            rowNum += 1

    return colorsDict

# writeColorsToLight
# in: A colors dictionary created from from the 'outputColorsFromMessage' subroutine (or in same format)
# out: Sends the specified colors to the lights
def writeColorsToLights(colorsDict, lightsArrayToMap):
    for light in lightsArrayToMap:
        urlString = '%slights/%s/state' % (BASEAPIURL, light)
        requests.put(urlString,\
                     json={'xy': [colorsDict[light][0], colorsDict[light][1]]})


# logError
# in: A string of the error location and a string of relevant details
# out: Error printed and logged in file
def logError(errLocation, errDetails):
    errLog = open('error.log', 'a+')

    errMessage = str(datetime.now()) + ': ' + errLocation + ': ' + errDetails + '\n' + str(sys.exc_info()) + '\n'

    print(errMessage)
    errLog.write(errMessage)

#MAIN
def main():
    textApiSession = establishApiConnection()
    messageQueue = []

    # Watch and respond to messages
    while True:
        
        # Update queue of messages
        try:
            messageQueue = updateMessageQueue(messageQueue, textApiSession)
        except:
            logError('Update Queue Error', str(len(messageQueue)))
            continue
        
        if(len(messageQueue) != 0):                                 # If messages exist:
            
            # Pull first message from queue
            try:
                currentMessage = messageQueue.pop()
                print('Processing Message: ' + currentMessage)
            except:
                logError('Message Pop Error', str(messageQueue))
                messageQueue = []
                continue
            
            # Remove unwanted chars from message
            try:
                currentMessage = cleanMessage(currentMessage)
            except:
                logError('Message Clean Error', currentMessage)
                continue
            
            # Download photo from Flickr based off message
            try:        
                messageToFlickrImage(currentMessage, 'photo.jpg')
            except:
                logError('Image Download Error', currentMessage)
                continue
            
            # Create color dict from photo
            try:
                colorsToWrite = outputColorsFromPhoto('photo.jpg')
            except:
                logError('Color Extraction Error', currentMessage)
                continue

            # Send colors to lights
            try:    
                writeColorsToLights(colorsToWrite, ALLLIGHTS)
                print('Message Processed')                 
            except:
                logError('Color Write Error', str(colorsToWrite))
        else:
            time.sleep(2)     # to avoid overwhelming API

main()