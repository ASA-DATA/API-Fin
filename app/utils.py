import psycopg2
import time
import pytz
import pandas as pd
import json
import copy
import os
import logging

from app import constants
from app import lists
from typing import Union
from datetime import datetime,timezone, timedelta

logger = logging.getLogger("uvicorn.error")

def GetDateFormat(value: str) -> str:
   '''
   From a given date or datetime string retrieve the dateformat.
   ``This is usefull to convert dates in string to datetime tuples.``
   ``value:`` date or datetime in string format 
   '''
   for dateFormat in lists.dateFormats:
      try:
         datetime.strptime(value, dateFormat)
         return dateFormat
      except ValueError:
         continue
   return False

def GetDateFromString(value: str) -> datetime:
   '''
   Convert the string date to a datetime tuple
   allowed formats 
   ('%Y-%m-%d %H:%M:%S.%f',
   '%Y-%m-%d %H:%M:%S',
   '%Y-%m-%d %H:%M',
   '%Y-%m-%d %H',
   '%Y-%m-%d')
   ``value: `` date string E.G. '10/20/2022 12:30:00'
   '''
   return datetime.strptime(value, GetDateFormat(value))

def GetStringFromDate(value: datetime, format: str) -> str:
   '''
   ``Convert`` the ``datetime`` tuple ``to`` a ``string`` date 
   allowed formats.
   ('%Y-%m-%d %H:%M:%S.%f',
   '%Y-%m-%d %H:%M:%S',
   '%Y-%m-%d %H:%M',
   '%Y-%m-%d %H',
   '%Y-%m-%d')
   ``value: `` datetime tupple.
   ``format: `` output format you need.
   '''
   return value.strftime(format)

def ConvertUTCToTimeZoneStamp(UTCTime:datetime, timeZone: str) -> datetime:
   '''
   From the given datetime tuple in UTC. Get the datetime of the requested timeZone.
   ``UTCTime:`` datetime tuple in UTC.
   ``timeZone:`` name of the timeZone E.G. "US/Central"
   '''
   return datetime(UTCTime.year, UTCTime.month, UTCTime.day, UTCTime.hour, UTCTime.minute, UTCTime.second, tzinfo=timezone.utc).astimezone(tz= pytz.timezone(timeZone)).replace(tzinfo=None)

def get_cv_data(query):
    print("Hola")
    conn = None
    start_time = time.time()
    #dbSection='cv-database'
    columnNames = []
    data = []

    try:
        
        #params = config(section=dbSection)
        params = {
            "host": os.getenv("DB_HOST"),
            "database": os.getenv("DB_NAME"),
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD"),
            "sslmode": "require",
        }

        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(query)

        columnNames = [x[0] for x in cur.description] if cur.description else []
        data = cur.fetchall()

        cur.close()

    except Exception:
        # 👇 ESTO ES LO CLAVE
        logger.exception("get_cv_data failed")

    finally:
        if conn is not None:
            conn.close()
            end_time = time.time()
            elapsed_time = end_time - start_time
            minutes, seconds = divmod(elapsed_time, 60)
            print(
                f"DB connection closed. "
                f"Elapsed time {int(minutes)} minutes and {seconds:.2f} seconds."
            )

    return columnNames, data
    
def get_location_info(dfLocations, fromDateString: Union[str, None] = None):
   aggregationTime=60
   data_dict= {}
   for _, row in dfLocations.iterrows():
         crossing=row["name_x"]
         location = row["name_y"]
         timeZone=row["time_zone"]
         tableName = row["table_name"]
         utcNow= datetime.now(pytz.utc) 
         selectQuery = ''
         selectClause = 'SELECT * '
         fromClause = f'''FROM {tableName} '''
         whereClause = 'WHERE'

         if fromDateString:
            toDateString=GetStringFromDate(GetDateFromString(fromDateString)+ timedelta(days=1),lists.dateFormats[-1])
            crossingCondition = f''' '{fromDateString}'<= time AND time <'{toDateString}' '''   
         else:
            fromDateString,toDateString=ConvertUTCToTimeZoneStamp(utcNow,timeZone).replace(hour=0, minute= 0, second= 0, microsecond=0), ConvertUTCToTimeZoneStamp(utcNow,timeZone)
            crossingCondition = f''' '{fromDateString}'<= time AND time<= '{toDateString}' '''
         
         selectQuery = selectClause + fromClause + whereClause + crossingCondition
         
         rawData= get_cv_data(selectQuery)
         rawDataDF=pd.DataFrame(rawData[1],columns=rawData[0])
         rawDataDF["time"] = rawDataDF["time"].dt.tz_convert("UTC").dt.tz_localize(None)
         fromDate,toDate=GetDateFromString(fromDateString), GetDateFromString(toDateString)

         iterNum= int((toDate-fromDate).total_seconds() / (60*aggregationTime))+1
         
         
         groupsOfClasses= getCrossingInfo(location,"groupsOfClasses")
         dataColumns= lists.dataColumns
         dfData = pd.DataFrame()
         
         dfData[dataColumns[0]] =[fromDate+timedelta(minutes=aggregationTime*(iter+1)) for iter in range(iterNum)]
         # data_chunk_group= data_chunk[data_chunk["class_name"].isin(group)]
         
         for index, objectGroup in enumerate(groupsOfClasses["listOfElements"]):
            
            groupName= groupsOfClasses["names"][index]
            data_grouped= rawDataDF[rawDataDF["class_name"].isin(objectGroup)]

            listCrossingNum= []
            listAvgSpeed= []
            listVehicleDwellTime= []
            listVZ= []
          
            for iter in range(iterNum):
               
               data_chunk=data_grouped[(data_grouped['time'] >= fromDate+timedelta(minutes=iter*aggregationTime)) & (data_grouped['time'] < fromDate+timedelta(minutes=(iter+1)*aggregationTime))]
               
               # Crossing count
               listCrossingNum.append(len(data_chunk.dropna(subset=["line_name"])))
               
               # Vehicles in zone          
               listVZ.append(len(set(list(data_chunk["track_id"].values))))

               # Speed                          
               listAvgSpeed.append(data_chunk[data_chunk["speed_mph"].isna() | (data_chunk["speed_mph"] == 0)]["speed_mph"].mean()  if not data_chunk.empty else 0)
               
               # Max dwell time
               maximo = data_chunk["dwell_seconds"].max()
               listVehicleDwellTime.append(0 if pd.isna(maximo) else maximo)

            dfData[dataColumns[1]+'_'+groupName]= listCrossingNum
            dfData[dataColumns[2]+'_'+groupName]= listVZ
            dfData[dataColumns[3]+'_'+groupName]= listAvgSpeed
            dfData[dataColumns[4]+'_'+groupName]= listVehicleDwellTime             
         data_dict[crossing+"_"+location]=parse_dataframe(dfData)
   return data_dict
   
def getCrossingInfo(location: Union[str,None] = None, classesInfo: Union[str,None] = None):
   '''
   Retrieve the Crossing's info JSON data. 
   is possible to get just the value from the given ``header`` or ``source`` or ``crossingName``.
   ``crossingName:`` which specific crossing.
   ``source:`` which project.
   ``header:`` which value under source
   '''
   crossingsInfo = get_cached_crossings_info()
   try:
      if location is None:
         return crossingsInfo
      if classesInfo is None:
         return crossingsInfo[location]
      else:
         return crossingsInfo[location][classesInfo] 
   except Exception:
      return {}   
   
cached_crossings_info = None

def get_cached_crossings_info():
   UTCCurrentDateTime = datetime.now(pytz.utc)
   global cached_crossings_info
   #refresh if more than 10mins
   if cached_crossings_info is None or (cached_crossings_info and (UTCCurrentDateTime - cached_crossings_info[0]) > timedelta(minutes=10)):
      #Load the JSON If is not in the cache
      cached_crossings_info = (UTCCurrentDateTime, readJSON(constants.PATH_JSON_CROSSINGS_INFO))
   
   return copy.deepcopy(cached_crossings_info[1])

def readJSON(file: str):
   '''
   Retrieves a dictionary from a json file
   ``file:`` file Location
   '''
   with open(file) as f:
      return json.load(f)
   
def parse_dataframe(df: pd.DataFrame) -> dict:
    # 🧹 elimina filas basura si aplica (equivalente a slice(2))
    df = df.iloc[2:].copy()

    # 🚫 elimina filas con NaN críticos
    df = df.dropna(subset=[df.columns[0]])

    # 🔄 convierte timestamp a string (JSON safe)
    df[df.columns[0]] = pd.to_datetime(df[df.columns[0]], errors="coerce")
    df = df.dropna(subset=[df.columns[0]])
    df[df.columns[0]] = df[df.columns[0]].dt.strftime("%Y-%m-%d %H:%M:%S")

    # 📊 chartData1 (Cross Count)
    chartData1 = [
        {
            "x": row[df.columns[0]],
            "y1": float(row[df.columns[1]]),  # POV
            "y2": float(row[df.columns[5]]),  # CMV
        }
        for _, row in df.iterrows()
    ]

    # 📊 chartData2 (Waiting Time)
    chartData2 = [
        {
            "x": row[df.columns[0]],
            "y1": float(row[df.columns[4]]),  # POV
            "y2": float(row[df.columns[8]]),  # CMV
        }
        for _, row in df.iterrows()
    ]

    # 📋 Summary table (última fila)
    last = df.iloc[-1]

    summaryTable = [
        [last[df.columns[0]], "CMV", "POV"],
        ["Number of vehicles that crossed the segment", int(last[df.columns[5]]), int(last[df.columns[1]])],
        ["Number of vehicles detected in the zone", int(last[df.columns[6]]), int(last[df.columns[2]])],
        ["Speed", float(last[df.columns[7]]), float(last[df.columns[3]])],
    ]

    return {
        "chartData1": chartData1,
        "chartData2": chartData2,
        "summaryTable": summaryTable,
    }   