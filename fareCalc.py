import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd #download ka panda sa bash type mo toh "pip install pandas"
from math import radians, sin, cos, sqrt, atan2
import requests
from io import BytesIO
from PIL import Image, ImageTk #download mo PIL sa bash type mo "pip install pillow"
import threading
import os

GOOGLE_MAPS_API_KEY = "AIzaSyA1e6h7uwjZYPzlNmbOrkEB0DdhHXKSQY0"

#global vars for map
currentZoom = 13
currentCenterLat = 14.5995  # Manila latitude, default loc
currentCenterLon = 120.9842  # Manila longitude, default loc
currentMapImage = None
isLoading = False
mapMode = "default"  #or "route"
currentOrigin = None
currentDestination = None
currentPolyline = None
panTimer = None
vehicleVar = None
discountVar = None  
currentOriginCoords = None
currentDestCoords = None
isShowingRoute = False

#panning using mouse
dragStartX = 0
dragStartY = 0
isDragging = False


def LoadGtfsData(): #load gtfs data from gtfs-master folder
    try:
        if not os.path.exists("gtfs-master (2)"): #check if folder exists
            ShowErrorMessage("GTFS Data Error", 
                             "gtfs-master folder not found. Please ensure the folder exists in the same directory as this script.")
            return None, None, None
        
        routes = pd.read_csv("gtfs-master (2)/gtfs-master/routes.txt") #load necessary gtfs files
        stops = pd.read_csv("gtfs-master (2)/gtfs-master/stops.txt")
        trips = pd.read_csv("gtfs-master (2)/gtfs-master/trips.txt")
        
        print(f"Loaded {len(routes)} routes, {len(stops)} stops, {len(trips)} trips")
        return routes, stops, trips
        
    except FileNotFoundError as e:
        ShowErrorMessage("GTFS Data Error", 
                         f"Missing GTFS data file: {str(e)}. Please ensure all required .txt files are in the gtfs-master folder.")
        return None, None, None
    except Exception as e:
        ShowErrorMessage("Data Loading Error", f"Error loading GTFS data: {str(e)}")
        return None, None, None

#map zooming 
def ZoomIn():
    global currentZoom
    if currentZoom < 20 and not isLoading:  #max zoom level = 20
        newZoom = currentZoom + 1
        threading.Thread(target=UpdateMapWithRoute, args=(newZoom,), daemon=True).start()

def ZoomOut():
    global currentZoom
    if currentZoom > 1 and not isLoading:  # min zoom = 1
        newZoom = currentZoom - 1
        threading.Thread(target=UpdateMapWithRoute, args=(newZoom,), daemon=True).start()

def ResetZoom():
    global currentZoom, currentCenterLat, currentCenterLon #reset the map to manila
    
    if not isLoading:
        currentZoom = 13  #default zoom
        
        if isShowingRoute and currentOriginCoords and currentDestCoords:
            #nagcacalculate ng center ng origin and destination para sa route display
            originLat, originLon = map(float, currentOriginCoords.split(','))
            destLat, destLon = map(float, currentDestCoords.split(','))
            
            currentCenterLat = (originLat + destLat) / 2
            currentCenterLon = (originLon + destLon) / 2
            
            #adjust zoom level para magfit yung route sa map display
            latDiff = abs(originLat - destLat)
            lonDiff = abs(originLon - destLon)
            
            maxDiff = max(latDiff, lonDiff) #appropriate zoom level based on distance
            if maxDiff > 0.1:  #long distance
                currentZoom = 11
            elif maxDiff > 0.05:  #sakto lang
                currentZoom = 12
            else:  #lapit lang
                currentZoom = 13
        else:
            #reset to default Manila view
            currentCenterLat = 14.5995
            currentCenterLon = 120.9842
        
        threading.Thread(target=UpdateMapWithRoute, args=(currentZoom,), daemon=True).start() #handle map updates and para di rin maglag yung UI while getting info from http request


def ScheduleMapUpdate(): #causes delayed map update to prevent excessive requests, ai lang toh kaya maraming notes
    global panTimer
    
    if panTimer is not None:
        root.after_cancel(panTimer) 
        #if meron nang existing pan timer, icacancel niya yung pag-pan mo to prevent multiple updates, yung last movement lang yung magttrigger ng update
    
    panTimer = root.after(500, lambda: threading.Thread( 
    #after the delay (500ms), creates and starts a new thread to update the map
        target=UpdateMapWithRoute,
        args=(currentZoom,),
        daemon=True #backgorund thread na automatically stops when the main program exits
    ).start())

def OnMapPress(event):
    global dragStartX, dragStartY, isDragging
    if not isLoading:
        dragStartX = event.x
        dragStartY = event.y
        isDragging = True

def OnMapDrag(event):
    global isDragging
    if isDragging and not isLoading:
        mapLabel.config(cursor="fleur")

def OnMapRelease(event):
    global dragStartX, dragStartY, isDragging, currentCenterLat, currentCenterLon
    
    if isDragging and not isLoading:
        isDragging = False
        mapLabel.config(cursor="")
        
        dragX = event.x - dragStartX
        dragY = event.y - dragStartY
        
        if abs(dragX) > 5 or abs(dragY) > 5:
            mapImageWidthPixels = 800
            mapImageHeightPixels = 500
            
            degreesPerPixelAtZoom = 360 / (256 * (2 ** currentZoom))
            
            deltaLon = (dragX / mapImageWidthPixels) * (mapImageWidthPixels * degreesPerPixelAtZoom)
            deltaLat = (dragY / mapImageHeightPixels) * (mapImageHeightPixels * degreesPerPixelAtZoom)
            
            currentCenterLon -= deltaLon
            currentCenterLat += deltaLat
            
            ScheduleMapUpdate()

#map loading and display
def UpdateMapAsync(zoom_level): #asynchronously loads the map and updates the display
    map_image = LoadMapWithZoom(GOOGLE_MAPS_API_KEY, zoom_level)
    if map_image:
        root.after(0, lambda: UpdateMapDisplay(map_image, zoom_level))

def UpdateMapDisplay(mapImage, zoomLevel): #updates map image and zoom label
    global currentZoom
    currentZoom = zoomLevel
    resizedMap = mapImage.resize((800, 500))
    tkImage = ImageTk.PhotoImage(resizedMap)
    mapLabel.config(image=tkImage)
    mapLabel.image = tkImage
    zoomLabel.config(text=f"Zoom: {currentZoom}")

def GetStaticMap(originCoords, destCoords, apiKey, zoom=None, center=None):
    if zoom is None:
        zoom = currentZoom

    if not apiKey:
        ShowErrorMessage("API Key Error", "Please set your Google Maps API key.")
        return None
    
    try:
        #get directions to get the route polyline. polyline will draw the route on the map
        directionsUrl = "https://maps.googleapis.com/maps/api/directions/json"
        directionsParams = {
            "origin": originCoords,
            "destination": destCoords,
            "mode": "transit",
            "key": apiKey
        }
        
        response = requests.get(directionsUrl, params=directionsParams, timeout=10)
        if response.status_code != 200:
            return GetSimpleStaticMap(center or originCoords, destCoords, apiKey, zoom)
        
        directionsData = response.json()
        
        #if transit fails, try driving mode
        if directionsData.get("status") != "OK":
            directionsParams["mode"] = "driving"
            response = requests.get(directionsUrl, params=directionsParams, timeout=10)
            directionsData = response.json()
        
        if directionsData.get("status") != "OK" or not directionsData.get("routes"):
            return GetSimpleStaticMap(center or originCoords, destCoords, apiKey, zoom)
        
        #extract polyline from directions
        route = directionsData["routes"][0]
        polyline = route["overview_polyline"]["points"]
        
        #create static map with route
        staticMapUrl = "https://maps.googleapis.com/maps/api/staticmap"
        staticParams = {
            "size": "800x600",
            "maptype": "roadmap",
            "markers": [
                f"color:green|label:A|{originCoords}",
                f"color:red|label:B|{destCoords}"
            ],
            "path": f"enc:{polyline}",
            "zoom": zoom,
            "key": apiKey
        }
        
        #add center if provided, ai lang din i2
        if center:
            staticParams["center"] = center
        
        mapResponse = requests.get(staticMapUrl, params=staticParams, timeout=10)
        if mapResponse.status_code == 200:
            return Image.open(BytesIO(mapResponse.content))
        else:
            return GetSimpleStaticMap(center or originCoords, destCoords, apiKey, zoom)
            
    except Exception as e:
        print(f"Error getting map with route: {e}")
        return GetSimpleStaticMap(center or originCoords, destCoords, apiKey, zoom)

def GetSimpleStaticMap(centerCoords, destCoords=None, apiKey=None, zoom=None): #get static map without route
    if zoom is None:
        zoom = currentZoom

    try:
        staticMapUrl = "https://maps.googleapis.com/maps/api/staticmap"
        staticParams = {
            "center": centerCoords,
            "size": "800x600",
            "maptype": "roadmap",
            "zoom": zoom,
            "key": apiKey
        }
        
        #add markers if may origin and destination coords
        markers = []
        if centerCoords:
            markers.append(f"color:green|label:A|{centerCoords}")
        if destCoords:
            markers.append(f"color:red|label:B|{destCoords}")
        
        if markers:
            staticParams["markers"] = markers
        
        response = requests.get(staticMapUrl, params=staticParams, timeout=10)
        if response.status_code == 200:
            return Image.open(BytesIO(response.content))
        else:
            print(f"Error getting simple map: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"Error getting simple map: {e}")
        return None

def LoadMapWithZoom(apiKey, zoomLevel, centerLat=None, centerLon=None): #loads the map with the specified zoom level
    global currentZoom, currentCenterLat, currentCenterLon, isLoading
    
    ShowLoading()
    currentZoom = zoomLevel
    
    if centerLat is not None and centerLon is not None:
        currentCenterLat = centerLat
        currentCenterLon = centerLon
    
    try:
        if isShowingRoute and currentOriginCoords and currentDestCoords:
            mapImage = GetStaticMap(
                currentOriginCoords,
                currentDestCoords,
                apiKey,
                zoomLevel,
                f"{currentCenterLat},{currentCenterLon}"
            )
        else:
            mapImage = GetSimpleStaticMap(
                f"{currentCenterLat},{currentCenterLon}",
                None,
                apiKey,
                zoomLevel
            )
        
        HideLoading()
        return mapImage
            
    except Exception as e:
        errorMsg = f"Error loading map: {e}"
        print(errorMsg)
        root.after(0, lambda: ShowErrorMessage("Map Loading Error", errorMsg))
        HideLoading()
        return None

def OnCalculate(): #fare calculation
    if isLoading:
        messagebox.showwarning("Please Wait", "Map is still loading...")
        return
        
    originName = originVar.get()
    destinationName = destinationVar.get()

    #validate inputs
    if originName == "" or destinationName == "":
        messagebox.showerror("Missing Input", "Please select both origin and destination stops.")
        return

    if originName == destinationName:
        messagebox.showerror("Invalid Input", "Origin and destination cannot be the same.")
        return

    #stop details from csv file
    originMatches = stopNames[stopNames['stop_name'] == originName]
    destMatches = stopNames[stopNames['stop_name'] == destinationName]
    
    if originMatches.empty or destMatches.empty:
        messagebox.showerror("Data Error", "Selected stop not found in GTFS data.")
        return

    originStop = originMatches.iloc[0]
    destinationStop = destMatches.iloc[0]

    #loading kineme
    ShowLoading()
    threading.Thread(target=LoadMapAsync, args=(originStop, destinationStop), daemon=True).start()

def LoadMapAsync(originStop, destStop): #load map in background thread
    global currentOriginCoords, currentDestCoords, isShowingRoute
    
    currentOriginCoords = f"{originStop['stop_lat']},{originStop['stop_lon']}"
    currentDestCoords = f"{destStop['stop_lat']},{destStop['stop_lon']}"
    isShowingRoute = True
    
    #get map image
    mapImage = GetStaticMap(currentOriginCoords, currentDestCoords, GOOGLE_MAPS_API_KEY)
    
    #calculate distance
    distance = CalculateDistance(
        originStop['stop_lat'], originStop['stop_lon'],
        destStop['stop_lat'], destStop['stop_lon']
    )
    
    #update UI in main thread
    root.after(0, lambda: UpdateResults(mapImage, distance))


def CalculateDistance(lat1, lon1, lat2, lon2): #calculate distance between two coordinates using Haversine formula
    R = 6371  #radius of Earth in km
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def CalculateFare(distanceTraveled, vehicleChoice, isDiscounted): #calculate fare with criterias
    vehicle = Vehicles[vehicleChoice]
    regularFare = vehicle["baseFare"]

    if distanceTraveled > vehicle["baseDistance"]:
        extraKm = int(distanceTraveled - vehicle["baseDistance"])
        regularFare += extraKm * vehicle["perKm"]

    discount = int(round(regularFare * 0.20)) if isDiscounted else 0
    totalFare = int(round(regularFare)) - discount

    return vehicle["name"], round(distanceTraveled, 2), int(round(regularFare)), discount, totalFare

def ShowLoading(): #for showing loading message
    global isLoading
    isLoading = True
    loadingLabel = tk.Label(mapLabel, text="Loading...", bg='white', fg='black')
    loadingLabel.place(relx=0.5, rely=0.1, anchor='center')
    loadingLabel.tag = "loading"
    root.update_idletasks()

def HideLoading(): #for hiding loading message
    global isLoading
    isLoading = False
    for widget in mapLabel.winfo_children():
        if hasattr(widget, 'tag') and widget.tag == "loading":
            widget.destroy()

def ShowErrorMessage(title, message): #for showing error messages
    messagebox.showerror(title, message)

def FilterCombobox(event, combobox, options): #filter combobos based on sa iinput ni user sa search bar
    value = combobox.get().lower()
    filtered = [option for option in options if value in option.lower()]
    combobox['values'] = filtered

def ClearInputs(): #clear all inputs and reset map
    global currentMapImage, currentOriginCoords, currentDestCoords, isShowingRoute
    
    originVar.set("")
    destinationVar.set("")
    vehicleVar.set(4)
    discountVar.set("no")
    
    fareSummaryText.config(state='normal')
    fareSummaryText.delete(1.0, tk.END)
    fareSummaryText.config(state='disabled')
    
    currentOriginCoords = None
    currentDestCoords = None
    isShowingRoute = False
    
    mapLabel.config(text="Select origin and destination to view route", image='')
    currentMapImage = None
    
    ResetZoom()

def UpdateResults(mapImage, distance): #update UI
    global currentMapImage
    
    #calculate fare
    vehicleChoice = vehicleVar.get()
    isDiscounted = discountVar.get().lower() == "yes"
    vehicleName, dist, regularFare, discount, totalFare = CalculateFare(distance, vehicleChoice, isDiscounted)

    #fare summary
    summary = (
        f"Vehicle Type        : {vehicleName}\n"
        f"Distance Traveled   : {dist:.2f} km\n"
        f"Regular Fare        : ₱{regularFare}\n"
        f"Discount Applied    : ₱{discount}\n"
        f"Total Fare         : ₱{totalFare}"
    )

    fareSummaryText.config(state='normal')
    fareSummaryText.delete(1.0, tk.END)
    fareSummaryText.insert(tk.END, summary)
    fareSummaryText.config(state='disabled')
    
    #update map display
    if mapImage:
        currentMapImage = mapImage
        resizedImage = mapImage.resize((800, 500), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(resizedImage)
        mapLabel.config(image=photo, text='')
        mapLabel.image = photo  # Keep a reference
    else:
        mapLabel.config(text="Map could not be loaded", image='')
    
    HideLoading()


#vehicle options
Vehicles = {
    1: {"name": "Airconditioned Bus", "baseFare": 15, "baseDistance": 5, "perKm": 3},
    2: {"name": "Ordinary Bus", "baseFare": 13, "baseDistance": 5, "perKm": 3},
    3: {"name": "Modern E-Jeepney", "baseFare": 15, "baseDistance": 4, "perKm": 3},
    4: {"name": "Traditional Jeepney", "baseFare": 13, "baseDistance": 4, "perKm": 2}
}

#gtfs data loading
routes, stops, trips = LoadGtfsData()
if routes is None:
    exit()

#stop coords
stops['stop_lat'] = stops['stop_lat'].astype(float)
stops['stop_lon'] = stops['stop_lon'].astype(float)

#stop names for dropdown
stopNames = stops[['stop_name', 'stop_lat', 'stop_lon']].drop_duplicates()
stopOptions = stopNames['stop_name'].unique().tolist()

#main window 
root = tk.Tk()
root.title("Fare Wise - with Interactive Map")
root.geometry("1000x1000")

#para maging scrollable
canvas = tk.Canvas(root, borderwidth=0, background="#f0f0f0")
scrollbar = tk.Scrollbar(root, orient="vertical", command=canvas.yview)
canvas.configure(yscrollcommand=scrollbar.set)

scrollbar.pack(side="right", fill="y")
canvas.pack(side="left", fill="both", expand=True)

#main frame inside canvas
mainFrame = tk.Frame(canvas, padx=20, pady=20)
canvas.create_window((0, 0), window=mainFrame, anchor="nw", width=canvas.winfo_width())

#configure column weights for centering
mainFrame.grid_columnconfigure(0, weight=1)
mainFrame.grid_rowconfigure(0, weight=1)

#configure scrolling
def onFrameConfigure(event):
    canvas.configure(scrollregion=canvas.bbox("all"))
    # Update the window width to match canvas
    canvas.itemconfig(canvas.find_withtag("all")[0], width=canvas.winfo_width())

mainFrame.bind("<Configure>", onFrameConfigure)

def onMouseWheel(event):
    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

canvas.bind_all("<MouseWheel>", onMouseWheel)

#container, centered
contentFrame = tk.Frame(mainFrame)
contentFrame.pack(expand=True)

#map display frame/section
mapFrame = tk.Frame(contentFrame)
mapFrame.pack(pady=(0, 20))

tk.Label(mapFrame, text="Interactive Route Map", font=("Arial", 12, "bold")).pack()

#container for the map and loading indicator
mapContainer = tk.Frame(mapFrame)
mapContainer.pack(pady=5)

#map display
mapLabel = tk.Label(mapContainer, bg='lightgray', text="Loading default map...")
mapLabel.pack(pady=5)

#bind mouse events for map dragging
mapLabel.bind("<Button-1>", OnMapPress)
mapLabel.bind("<B1-Motion>", OnMapDrag)
mapLabel.bind("<ButtonRelease-1>", OnMapRelease)

#map controls - center align
controlFrame = tk.Frame(mapFrame)
controlFrame.pack(pady=5)

#zoom controls
zoomFrame = tk.Frame(controlFrame)
zoomFrame.pack(pady=2)

zoomInBtn = tk.Button(zoomFrame, text="Zoom In (+)", command=ZoomIn, width=10)
zoomInBtn.pack(side='left', padx=2)

zoomOutBtn = tk.Button(zoomFrame, text="Zoom Out (-)", command=ZoomOut, width=10)
zoomOutBtn.pack(side='left', padx=2)

resetZoomBtn = tk.Button(zoomFrame, text="Reset View", command=ResetZoom, width=10)
resetZoomBtn.pack(side='left', padx=2)

#zoom level indicator 
zoomLabel = tk.Label(mapFrame, text=f"Zoom: {currentZoom}", font=("Arial", 9))
zoomLabel.pack(pady=2)

#usr input frame
inputFrame = tk.Frame(contentFrame)
inputFrame.pack(pady=(0, 20))

#origin and destination selection frame
locationFrame = tk.Frame(inputFrame, width=600)
locationFrame.pack(pady=(5, 15))
locationFrame.grid_columnconfigure(1, weight=1)
locationFrame.pack_propagate(False)

#origin 
tk.Label(locationFrame, text="Origin:", anchor='e', width=15).grid(row=0, column=0, sticky='e', pady=5)
originVar = tk.StringVar()
originDropdown = ttk.Combobox(locationFrame, textvariable=originVar, width=50)
originDropdown['values'] = stopOptions
originDropdown.grid(row=0, column=1, sticky='w', padx=(5, 0), pady=5)
originDropdown.bind("<KeyRelease>", lambda event: FilterCombobox(event, originDropdown, stopOptions))

#destination
tk.Label(locationFrame, text="Destination:", anchor='e', width=15).grid(row=1, column=0, sticky='e', pady=5)
destinationVar = tk.StringVar()
destinationDropdown = ttk.Combobox(locationFrame, textvariable=destinationVar, width=50)
destinationDropdown['values'] = stopOptions
destinationDropdown.grid(row=1, column=1, sticky='w', padx=(5, 0), pady=5)
destinationDropdown.bind("<KeyRelease>", lambda event: FilterCombobox(event, destinationDropdown, stopOptions))

#vehicle type
vehicleVar = tk.IntVar(value=4)  # Initialize here
vehicleLabelFrame = tk.Frame(inputFrame)
vehicleLabelFrame.pack()
tk.Label(vehicleLabelFrame, text="Vehicle Type:").pack(pady=(0, 5))

vehicleFrame = tk.Frame(inputFrame)
vehicleFrame.pack()
for val, vehicle in Vehicles.items():
    tk.Radiobutton(vehicleFrame, text=vehicle["name"], variable=vehicleVar, value=val).pack(anchor='center')

#discount
discountVar = tk.StringVar(value="no")  #default value is no
discountLabelFrame = tk.Frame(inputFrame)
discountLabelFrame.pack()
tk.Label(discountLabelFrame, text="Student/Senior/PWD Discount:").pack(pady=(15, 5))

discountFrame = tk.Frame(inputFrame)
discountFrame.pack()
radioFrame = tk.Frame(discountFrame)
radioFrame.pack()
tk.Radiobutton(radioFrame, text="Yes", variable=discountVar, value="yes").pack(side='left', padx=10)
tk.Radiobutton(radioFrame, text="No", variable=discountVar, value="no").pack(side='left', padx=10)

#buttons
buttonFrame = tk.Frame(inputFrame)
buttonFrame.pack(pady=15)

calcButton = tk.Button(buttonFrame, text="Calculate Fare & Show Route", command=OnCalculate, width=25)
calcButton.pack(side='left', padx=5)

clearButton = tk.Button(buttonFrame, text="Clear", command=ClearInputs, width=15)
clearButton.pack(side='left', padx=5)

#fare summary frame
summaryLabelFrame = tk.Frame(inputFrame)
summaryLabelFrame.pack()
tk.Label(summaryLabelFrame, text="Fare Summary", font=("Arial", 10, "bold")).pack(pady=(20, 5))

fareSummaryText = tk.Text(inputFrame, height=6, width=70, state='disabled', bg='#f0f0f0')
fareSummaryText.pack(pady=5)

# Add this function after the MAP LOADING AND DISPLAY section
def ShowDefaultMap(): #default map display
    global currentMapImage
    
    try:
        # Get default map centered on Manila
        mapImage = GetSimpleStaticMap(
            f"{currentCenterLat},{currentCenterLon}",
            None,
            GOOGLE_MAPS_API_KEY,
            currentZoom
        )
        
        if mapImage:
            currentMapImage = mapImage
            resizedImage = mapImage.resize((800, 500), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(resizedImage)
            mapLabel.config(image=photo, text='')
            mapLabel.image = photo
        else:
            mapLabel.config(text="Default map could not be loaded", image='')
            
    except Exception as e:
        print(f"Error loading default map: {e}")
        mapLabel.config(text="Error loading default map", image='')

ShowDefaultMap()

def UpdateMapWithRoute(zoomLevel): #update map with route
    global currentMapImage
    
    try:
        if isShowingRoute and currentOriginCoords and currentDestCoords: #if showing route, maintain the route display kahit ipan or zoom
            #get static map with route polyline
            mapImage = GetStaticMap(
                currentOriginCoords,
                currentDestCoords,
                GOOGLE_MAPS_API_KEY,
                zoomLevel,
                f"{currentCenterLat},{currentCenterLon}"  # Add current center
            )
        else:
            # Otherwise show regular map
            mapImage = GetSimpleStaticMap(
                f"{currentCenterLat},{currentCenterLon}",
                None,
                GOOGLE_MAPS_API_KEY,
                zoomLevel
            )
            
        if mapImage:
            currentMapImage = mapImage
            root.after(0, lambda: UpdateMapDisplay(mapImage, zoomLevel))
            
    except Exception as e:
        print(f"Error updating map: {e}")

root.mainloop() 