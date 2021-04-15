#!/usr/bin/env python3
#
###############################################################################
# Original Author: A.J. Rubio-Montero (http://orcid.org/0000-0001-6497-753X), #
#          CIEMAT - Sci-Track Group (http://rdgroups.ciemat.es/web/sci-track),#
#          for the EOSC-Synergy project (EU H2020 RI Grant No 857647).        #
# License (SPDX): BSD-3-Clause (https://opensource.org/licenses/BSD-3-Clause) #
# Copyright (c): 2020-today, The LAGO Collaboration (http://lagoproject.net)  #
###############################################################################


# additional modules needed
# apt-get install python3-xattr
# or yum install -y python36-pyxattr
import os
import xattr
import json
import datetime
import shutil
import time

from threading import Thread
from queue import Queue

#
from arguments import get_sys_args, _run_Popen, _run_Popen_interactive

onedataSimPath = os.path.dirname(os.path.abspath(__file__))


# ----- utils -----

def _write_file(filepath, txt):
    
    with open(filepath, 'w+') as file1:
        file1.write(txt)
        
        

def _xsd_dateTime():

    # xsd:dateTime
    # CCYY-MM-DDThh:mm:ss.sss[Z|(+|-)hh:mm]
    # The time zone may be specified as Z (UTC) or (+|-)hh:mm.
    return str(datetime.datetime.utcnow()).replace(' ', 'T')+'Z'


# j is adding j_new terms to existing keys or adding keys.
# j and j_new must have same structure (pruned) tree
# (dict.update adds only when key not exist, otherwise replace)
def _add_json(j, j_new):

    if type(j) is list:
        if type(j_new) is list:
            j += j_new
            return j
        return j.append(j_new)

    if (type(j) is dict) and (type(j_new) is dict):
        k_old = j.keys()
        for k, v in j_new.items():
            if k in k_old:
                j[k] = _add_json(j[k], v)
            else:
                j[k] = v
        return j

    # is not a list or a dict, is a term.
    # I change to list and call recursiveness
    return _add_json([j], j_new)

def _replace_common_patterns(s, catcodename, arti_params_dict):

    s = s.replace('CATCODENAME', catcodename)
    s = s.replace('ORCID', arti_params_dict['u'])
    # private generated by arguments.py
    s = s.replace('COMMITSHAARTI', arti_params_dict['priv_articommit'])
    s = s.replace('COMMITSHAODSIM', arti_params_dict['priv_odsimcommit'])
    s = s.replace('HANDLEJSONAPI', arti_params_dict['priv_handlejsonapi'])
    s = s.replace('HANDLECDMI', arti_params_dict['priv_handlecdmi'])
    s = s.replace('LANDINGPAGE', arti_params_dict['priv_landingpage'])
    return s

# ----- end utils -----

def get_first_catalog_metadata_json(catcodename, arti_params_dict):

    with open(onedataSimPath+'/json_tpl/common_context.json', 'r') as file1:
        with open(onedataSimPath+'/json_tpl/catalog_corsika.json',
                  'r') as file2:
            j = json.loads(file1.read())
            j = _add_json(j, json.loads(file2.read()))
            s = json.dumps(j)
            s = _replace_common_patterns(s, catcodename, arti_params_dict)
            return json.loads(s)


def get_catalog_metadata_activity(startdate, enddate, arti_params_dict):

    with open(onedataSimPath+'/json_tpl/catalog_corsika_activity.json',
              'r') as file1:
        j = json.loads(file1.read())
        s = json.dumps(j)
        s = s.replace('STARTDATE', startdate)
        s = s.replace('ENDDATE', enddate)
        s = _replace_common_patterns(s, catcodename, arti_params_dict)
        return s


######
def _get_common_metadata_aux():

    with open(onedataSimPath+'/json_tpl/common_context.json', 'r') as file1:
        with open(onedataSimPath+'/json_tpl/common_dataset.json',
                  'r') as file2:
            j = json.loads(file1.read())
            j = _add_json(j, json.loads(file2.read()))
            return j


def _get_input_metadata(filecode):

    with open(onedataSimPath+'/json_tpl/dataset_corsika_input.json',
              'r') as file1:
        j = _get_common_metadata_aux()
        j = _add_json(j, json.loads(file1.read()))
        s = json.dumps(j)
        s = s.replace('FILENAME', 'DAT'+filecode+'.input')
        # warning, corsikainput metadata must be included also...
        return s


def _get_bin_output_metadata(filecode):

    with open(onedataSimPath+'/json_tpl/common_dataset_corsika_output.json',
              'r') as file1:
        with open(onedataSimPath +
                  '/json_tpl/dataset_corsika_bin_output.json',
                  'r') as file2:
            j = _get_common_metadata_aux()
            j = _add_json(j, json.loads(file1.read()))
            j = _add_json(j, json.loads(file2.read()))
            s = json.dumps(j)
            runnr = filecode.split('-')[0]
            s = s.replace('FILENAME', 'DAT'+runnr+'.bz2')
            return s


def _get_lst_output_metadata(filecode):

    with open(onedataSimPath+'/json_tpl/common_dataset_corsika_output.json',
              'r') as file1:
        with open(onedataSimPath +
                  '/json_tpl/dataset_corsika_lst_output.json',
                  'r') as file2:
            j = _get_common_metadata_aux()
            j = _add_json(j, json.loads(file1.read()))
            j = _add_json(j, json.loads(file2.read()))
            s = json.dumps(j)
            s = s.replace('FILENAME', 'DAT'+filecode+'.lst.bz2')
            # falta comprimir si fuera necesario
            return s


def get_dataset_metadata(catcodename, filecode, startdate, end_date,
                         arti_params_dict):

    mdlistaux = [_get_bin_output_metadata(filecode),
                 _get_lst_output_metadata(filecode),
                 _get_input_metadata(filecode)]
    mdlist = []
    for s in mdlistaux:
        s = _replace_common_patterns(s, catcodename, arti_params_dict)
        s = s.replace('NRUN', filecode)
        s = s.replace('STARTDATE', startdate)
        s = s.replace('ENDDATE', end_date)
        mdlist.append(s)
    return mdlist


#########

# ------------ queue operations trhough oneclient -----------
q_onedata = Queue()

def _consumer_onedata_mv(onedata_path):
   
    while True:
        md = q_onedata.get()
        try:
            id = json.loads(md)['@id']
            # oneclient change the filename owner when you move it to
            # onedata and this action raise exceptions with shutil.move()
            # shutil.move('.' + id, onedata_path + id)
            cmd = "mv ." + id + " " + onedata_path + id
            _run_Popen(cmd)
            xattr.setxattr(onedata_path + id, 'onedata_json', md)
            id_hidden = '/' + id.lstrip('/').replace('/','/.metadata/.')
            _write_file(onedata_path + id_hidden + '.jsonld', md)
            q_onedata.task_done()
        except Exception as inst:
            q_onedata.put(md)
            time.sleep(2)

            
            
def _run_check_and_copy_results(catcodename, filecode, task, onedata_path,
                                arti_params_dict):

    # check if the results are already in onedata before running the task
    runtask = False
    mdlist_prev = get_dataset_metadata(catcodename, filecode,
                                       _xsd_dateTime(), _xsd_dateTime(),
                                       arti_params_dict)
    for md in mdlist_prev:
        id = json.loads(md)['@id']
        # We should also check if the existent metadata is well formed
        f = onedata_path + id
        # print("Check if exist: " + f)  
        if not os.path.exists(f):
            print("This result does not exist in onedata: " + f)
            print("Thus... I will RUN : " + filecode)
            runtask = True
            break

    if not runtask:
        print("Results already in OneData, none to do with RUN : " + filecode)
    else:
        try:
            start_date = _xsd_dateTime()
            _run_Popen(task)
            metadatalist = get_dataset_metadata(catcodename, filecode, 
                                                start_date, _xsd_dateTime(),
                                                arti_params_dict)
            
            for md in metadatalist:
                q_onedata.put(md)
        except Exception as inst:
            raise inst

 

# ------------ producer/consumer ---------
main_start_date = _xsd_dateTime()
q = Queue()


def _producer(catcodename, arti_params):

    # clean a possible previous simulation
    if os.path.exists(catcodename):
        shutil.rmtree(catcodename, ignore_errors=True)

    cmd = 'do_sims.sh ' + arti_params
    _run_Popen_interactive(cmd)

    # WARNING, I HAD TO PATCH rain.pl FOR AVOID SCREEN !!!!
    cmd = "sed 's/screen -d -m -a -S \$name \$script; screen -ls/\$script/' " + \
       " rain.pl -i"
    _run_Popen(cmd)
    
    # WARNING, I HAD TO PATCH rain.pl FOR AVOID .long files !!!
    cmd = "sed 's/\$llongi /F /' rain.pl -i"
    _run_Popen(cmd)

    # -g only creates .input's
    # cmd="sed 's/\.\/rain.pl/echo \$i: \.\/rain.pl -g /' go-*.sh  -i"
    cmd = "sed 's/\.\/rain.pl/echo \$i: \.\/rain.pl /' go-*.sh  -i"
    _run_Popen(cmd)
    cmd = "cat go-*.sh | bash  2>/dev/null"
    lines = _run_Popen(cmd).decode("utf-8").split('\n')
    for z in lines:
        if z != "":
            print(z)
            z_aux = z.split(":")
            runnr = z_aux[0]
            # prmpar name only allows 4 characters, we use zfill to fill with
            #  0's and limit to 4 characters if were needed.
            prmpar = str(int(runnr)).zfill(4)[-4:]
            task = z_aux[1]
            z_aux = task.split(catcodename)
            s_aux = z_aux[1].replace('/', '')
            s_aux = z_aux[1].replace('.run', '')
            z_aux = s_aux.split('-')
            filecode = runnr+'-'+prmpar+'-'+z_aux[1]
            q.put((filecode, task))


def _consumer(catcodename, onedata_path, arti_params_dict):
    while True:
        (filecode, task) = q.get()
        try:
            _run_check_and_copy_results(catcodename, filecode, task,
                                        onedata_path, arti_params_dict)
            print('Completed NRUN: ' + str(filecode) + '  ' + task)
            q.task_done()
        except Exception as inst:
            q.put((filecode, task))


# ------------ main stuff ---------
(arti_params, arti_params_dict, arti_params_json_md) = get_sys_args()
catcodename = arti_params_dict["p"]
# onedata_path = '/mnt/datahub.egi.eu/LAGOsim'
onedata_path = '/mnt/datahub.egi.eu/test8/LAGOSIM'
catalog_path = onedata_path + '/' + catcodename

print(arti_params, arti_params_dict, arti_params_json_md)

try:
    # mount OneData (fails in python although you wait forever):
    # removed, currently in Dockerfile.
    # cmd = "oneclient --force-proxy-io /mnt"
    # _run_Popen(cmd, timeout=10)
    if os.path.exists(onedata_path):
        if not os.path.exists(catalog_path):
            os.mkdir(catalog_path, mode=0o755) # this should change to 0700
            os.mkdir(catalog_path + '/.metadata', mode=0o755) # idem to 0700
            md = get_first_catalog_metadata_json(catcodename, 
                                                 arti_params_dict)
            md = _add_json(md, arti_params_json_md)
            _write_file(catalog_path + '/.metadata/.' + catcodename + '.jsonld',
                        json.dumps(md))
            xattr.setxattr(catalog_path, 'onedata_json', json.dumps(md))
        else: 
            if not os.access(catalog_path, os.W_OK):
                # It is needed managing this with some kind of versioning
                # or completion of failed simulations
                raise Exception("Simulation blocked by other user in" + \
                                " OneData: " + catalog_path)
    else:
        raise Exception("OneData not mounted")
except Exception as inst:
    raise inst

for i in range(int(arti_params_dict["j"])):  # processors
    t = Thread(target=_consumer, args=(catcodename, onedata_path,
                                       arti_params_dict))
    t.daemon = True
    t.start()

_producer(catcodename, arti_params)

t = Thread(target=_consumer_onedata_mv, args=(onedata_path,))
t.daemon = True
t.start()

q.join()
q_onedata.join()


md = json.loads(xattr.getxattr(catalog_path, 'onedata_json'))

# I'm replacing, not adding datasets. 
md['dataset'] = ["/" + catcodename + "/" + s for s in 
                 os.listdir(catalog_path) if not s.startswith('.')]

md = _add_json(md, json.loads(get_catalog_metadata_activity(main_start_date,
                                                            _xsd_dateTime(),
                                                            arti_params_dict)))

_write_file(catalog_path + '/.metadata/.' + catcodename + '.jsonld',
            json.dumps(md))
xattr.setxattr(catalog_path, 'onedata_json', json.dumps(md))
