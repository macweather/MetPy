#!/usr/bin/env python
from cStringIO import StringIO
import numpy as np
from numpy.ma import mrecords
from metpy.cbook import loadtxt, mloadtxt #Can go back to numpy once it's updated
from metpy.cbook import is_string_like, lru_cache, rec_append_fields

#This is a direct copy and paste of the mesonet station data avaiable at
#http://www.mesonet.org/sites/geomeso.csv
#As of November 20th, 2008
mesonet_station_table = '''
  100   2008 08 12  GEOMESO.TBL
'''

mesonet_vars = ['STID', 'STNM', 'TIME', 'RELH', 'TAIR', 'WSPD', 'WVEC', 'WDIR',
    'WDSD', 'WSSD', 'WMAX', 'RAIN', 'PRES', 'SRAD', 'TA9M', 'WS2M', 'TS10',
    'TB10', 'TS05', 'TB05', 'TS30', 'TR05', 'TR25', 'TR60', 'TR75']

#Map of standard variable names to those use by the mesonet
mesonet_var_map = {'temperature':'TAIR', 'relative humidity':'RELH',
    'wind speed':'WSPD', 'wind direction':'WDIR', 'rainfall':'RAIN',
    'pressure':'PRES', 'site':'STID', 'solar radiation':'SRAD',
    'wind gusts':'WMAX'}
mesonet_inv_var_map = dict(zip(mesonet_var_map.values(),
    mesonet_var_map.keys()))

mesonet_units = {'TAIR':'C', 'RELH':'%', 'PRES':'mb', 'WSPD':'m/s',
    'SRAD':'$W/m^2$', 'RAIN':'mm', 'WDIR':'deg', 'WMAX':'m/s'}

#Some special numbers
BAD_DATA_LIMIT = -990
FUTURE_OBSERVATION = -996

@lru_cache(maxsize=20)
def _fetch_mesonet_data(date_time, site=None):
    '''
    Helper function for fetching mesonet data from a remote location.
    Uses an LRU cache.
    '''
    import urllib2

    if site is None:
        data_type = 'mdf'
        #Put time back to last even 5 minutes
        date_time = date_time.replace(minute=(dt.minute - dt.minute%5),
            second=0, microsecond=0)
        fname = '%s.mdf' % date_time.strftime('%Y%m%d%H%M')
    else:
        data_type = 'mts'
        fname = '%s%s.mts' % (date_time.strftime('%Y%m%d'), site.lower())

    #Create the various parts of the URL and assemble them together
    path = '/%s/%04d/%02d/%02d/' % (data_type, date_time.year, date_time.month,
        date_time.day)
    baseurl='http://www.mesonet.org/public/data/getfile.php?dir=%s&filename=%s'

    #Open the remote location
    datafile = urllib2.urlopen(baseurl % (path+fname, fname))

    return datafile.read()

def remote_mesonet_data(date_time=None, fields=None, site=None,
    rename_fields=False, convert_time=True, lookup_stids=True,
    full_day_record=True):
    '''
    Reads in Oklahoma Mesonet Datafile (MDF) directly from their servers.

    date_time : datetime object
        A python :class:`datetime` object specify that date and time
        for which that data should be downloaded.  For a times series
        data, this only needs to be a date.  For snapshot files, this is
        the time to the nearest five minutes.

    fields : sequence
        A list of the variables which should be returned.  See
        :func:`read_mesonet_ts` for a list of valid fields.

    site : string
        Optional station id for the data to be fetched.  This is
        case-insensitive.  If specified, a time series file will be
        downloaded.  If left blank, a snapshot data file for the whole
        network is downloaded.

    rename_fields : boolean
        Flag indicating whether the field names given by the mesonet
        should be renamed to standard names. Defaults to False.

    convert_time : boolean
        Flag indicating whether the time reported in the file, which is
        in minutes since midnight of the files date, should be converted
        to a datetime.datetime object using the date reported at the top
        of the file. Defaults to True.

    lookup_stids : boolean
        Flag indicating whether to lookup the location for the station id
        and include this information in the returned data. Defaults to True.

    full_day_record : boolean
        Flag indicating whether to get yesterday's data as well as today's,
        when datetime is None.  This will give a full 24 hour of data, as
        opposed to just today's (incomplete) set.

    Returns : array
        A nfield by ntime masked array.  nfield is the number of fields
        requested and ntime is the number of times in the file.  Each
        variable is a row in the array.  The variables are returned in
        the order given in *fields*.
    '''
    #If we don't get a date, and therefore are using today, fetch yesterday's
    #data too so that we can have a full 24 hour record
    yest = None
    if date_time is None:
        import datetime
        date_time = datetime.datetime.utcnow()
        if full_day_record:
            yest = date_time - datetime.timedelta(days=1)

            old_data = StringIO(_fetch_mesonet_data(yest, site))
            old_data = read_mesonet_data(old_data, fields, rename_fields,
                convert_time, lookup_stids)

    #Fetch the data and read it in
    data = StringIO(_fetch_mesonet_data(date_time, site))
    data = read_mesonet_data(data, fields, rename_fields, convert_time,
        lookup_stids)

    if yest:
        # Need to create a new array.  Resizing the old ones will not work.
        final_data = np.ma.empty(old_data.size + data.size, dtype=data.dtype)
        final_data[:old_data.size] = old_data
        final_data[old_data.size:] = data
        data = final_data

    return data

def read_mesonet_data(filename, fields=None, rename_fields=False,
    convert_time=True, lookup_stids=True):
    '''
    Reads Oklahoma Mesonet data from *filename*.

    filename : string or file-like object
        Location of data. Can be anything compatible with
        :func:`numpy.loadtxt`, including a filename or a file-like
        object.

    fields : sequence
        List of fields to read from file.  (Case insensitive)
        Valid fields are:
            STID, STNM, TIME, RELH, TAIR, WSPD, WVEC, WDIR, WDSD,
            WSSD, WMAX, RAIN, PRES, SRAD, TA9M, WS2M, TS10, TB10,
            TS05, TB05, TS30, TR05, TR25, TR60, TR75
        The default is to return all fields.

    rename_fields : boolean
        Flag indicating whether the field names given by the mesonet
        should be renamed to standard names. Defaults to False.

    convert_time : boolean
        Flag indicating whether the time reported in the file, which is
        in minutes since midnight of the files date, should be converted
        to a datetime.datetime object using the date reported at the top
        of the file. Defaults to True.

    lookup_stids : boolean
        Flag indicating whether to lookup the location for the station id
        and include this information in the returned data. Defaults to True.

    Returns : array
        A nfield by ntime masked array.  nfield is the number of fields
        requested and ntime is the number of times in the file.  Each
        variable is a row in the array.  The variables are returned in
        the order given in *fields*.
    '''
    from datetime import datetime, timedelta

    if is_string_like(filename):
        if filename.endswith('.gz'):
            import gzip
            fh = gzip.open(filename)
        elif filename.endswith('.bz2'):
            import bz2
            fh = bz2.BZ2File(filename)
        else:
            fh = file(filename)
    elif hasattr(filename, 'readline'):
        fh = filename
    else:
        raise ValueError('filename must be a string or file handle')

    if fields:
        fields = map(str.upper, fields)

    #If we're converting the time, we need to read the 2nd line of the file
    #and parse that into a date object.  We use this object with a timedelta
    #to make a custom converter.  We also need to then tell the reader to no
    #longer skip any rows.
    if convert_time:
        #Skip first line, read the second for the date
        fh.readline()
        info = fh.readline().split()
        dt = datetime(*map(int, info[1:4]))
        skip = 0
        conv = {'TIME': lambda t: dt + timedelta(minutes=int(t))}
    else:
        skip = 2
        conv = None

    missing = ','.join(map(str,range(BAD_DATA_LIMIT, BAD_DATA_LIMIT-10, -1)))
    data = mloadtxt(fh, dtype=None, names=True, usecols=fields, skiprows=skip,
        converters=conv, missing=missing)

    #Use the inverted dictionary to map names in the FILE to their more
    #descriptive counterparts
    if rename_fields:
        names = data.dtype.names
        new_names = [mesonet_inv_var_map.get(n.upper(), n) for n in names]
        data.dtype.names = new_names
        data.mask.dtype.names = new_names

    #Change converted column name from TIME to datetime
    if convert_time:
        names = list(data.dtype.names)
        names[names.index('TIME')] = 'datetime'
        data.dtype.names = names
        data.mask.dtype.names = names

    #Lookup station information so that returned data has latitude and
    #longitude information
    if lookup_stids:
        sta_table = mesonet_stid_info()
        station_indices = sta_table['stid'].searchsorted(data['STID'])
        lat = sta_table['Lat'][station_indices]
        lon = sta_table['Lon'][station_indices]
        elev = sta_table['Elev'][station_indices]
        data = rec_append_fields(data, ('latitude', 'longitude', 'elevation'),
            (lat, lon, elev))

    return data

def mesonet_stid_info(info=None):
    '''
    Get mesonet station information.

    info : sequence of tuples
        Sequence of column name and number pairs, specifying
        what information to return.  The default of None returns
        station ID, latitude, longitude, and elevation.

    Returns : structured array
        A structured array with the station information.
    '''

    if info is None:
        names = ['stid', 'Lat', 'Lon', 'Elev']
        cols = (1, 7, 8, 9)
    else:
        names,cols = zip(*info)

    return loadtxt(StringIO(mesonet_station_table), dtype=None, skiprows=123,
        usecols=cols, names=names, delimiter=',')

def get_last_time(data, ref_field='TAIR', dt_field='datetime'):
    '''
    Get the time of the last actual observation in a mesonet file.

    data : structured array
        The mesonet data

    ref_field : string
        The name of the field in which to look to find where future
        observations are marked.  This defaults to 'TAIR'.

    dt_field : string
        The name of the field containing date/time information. Defaults
        to 'datetime'.

    Returns : the date/time of the last actual observation in the file
    '''
    mask = data[ref_field].data != FUTURE_OBSERVATION
    return data[dt_field][mask][-1]

if __name__ == '__main__':
    import datetime
    from optparse import OptionParser

    import matplotlib.pyplot as plt
    import scipy.constants as sconsts
    from metpy.vis import meteogram
    from metpy.constants import C2F
    from metpy.calc import dewpoint, windchill

    #Create a command line option parser so we can pass in site and/or date
    parser = OptionParser()
    parser.add_option('-s', '--site', dest='site', help='get data for SITE',
        metavar='SITE', default='nrmn')
    parser.add_option('-d', '--date', dest='date', help='get data for YYYYMMDD',
        metavar='YYYYMMDD', default=None)

    #Parse the command line options and convert them to useful values
    opts,args = parser.parse_args()
    if opts.date is not None:
        dt = datetime.datetime.strptime(opts.date, '%Y%m%d')
    else:
        dt = None

    fields = ('stid', 'time', 'relh', 'tair', 'wspd', 'wmax', 'wdir', 'pres',
        'srad', 'rain')

    data = remote_mesonet_data(dt, fields, opts.site, rename_fields=False,
        lookup_stids=False)

    #Add a reasonable time range if we're doing current data
    if dt is None:
        end = get_last_time(data)
        times = (end - datetime.timedelta(hours=24), end)
    else:
        times = None

    #Calculate dewpoint in F from relative humidity and temperature
    dewpt = C2F(dewpoint(data['TAIR'], data['RELH']/100.))
    data = rec_append_fields(data, ('dewpoint',), (dewpt,))

    #Convert temperature and dewpoint to Farenheit
    mod_units = mesonet_units.copy()
    mod_units['TAIR'] = 'F'
    mod_units['dewpoint'] = 'F'
    data['TAIR'] = C2F(data['TAIR'])

    #Convert wind speeds to MPH
    data['WSPD'] *= sconsts.hour / sconsts.mile
    data['WMAX'] *= sconsts.hour / sconsts.mile
    mod_units['WSPD'] = 'MPH'
    mod_units['WMAX'] = 'MPH'

    #Convert rainfall to inches
    data['RAIN'] *= sconsts.milli / sconsts.inch
    mod_units['RAIN'] = 'in.'

    #Calculate windchill
    wchill = windchill(data['TAIR'], data['WSPD'], metric=False)
    data = rec_append_fields(data, ('windchill',), (wchill,))

    fig = plt.figure(figsize=(8,10))
    layout = {0:['TAIR', 'dewpoint', 'windchill']}
    axs = meteogram(data, fig, field_info=mesonet_var_map, units=mod_units,
        time_range=times, layout=layout)
    axs[0].set_ylabel('Temperature (F)')
    plt.show()