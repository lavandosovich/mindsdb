import json
import datetime
from dateutil.parser import parse as parse_dt
import shutil
import os
import pickle
import sys
import resource

import mindsdb

from mindsdb_server.interfaces.datastore.sqlite_helpers import *
from mindsdb_server.interfaces.native.mindsdb import MindsdbNative
from mindsdb import FileDS, ClickhouseDS
from mindsdb_server.interfaces.datastore.sqlite_helpers import create_sqlite_db


class DataStore():
    def __init__(self, config=None, storage_dir=None):
        print(config)
        self.dir = storage_dir if isinstance(storage_dir, str) else config['data_store_path']
        self.mindsdb_native = MindsdbNative(config)

    def get_analysis(self, ds):
        return self.mindsdb_native.analyse_dataset(ds)

    def get_datasources(self):
        datasource_arr = []
        for ds_name in os.listdir(self.dir):
            try:
                with open(os.path.join(self.dir, ds_name, 'datasource', 'metadata.json'), 'r') as fp:
                    try:
                        datasource = json.load(fp)
                        datasource['created_at'] = parse_dt(datasource['created_at'].split('.')[0])
                        datasource['updated_at'] = parse_dt(datasource['updated_at'].split('.')[0])
                        datasource_arr.append(datasource)
                    except Exception as e:
                        print(e)
            except Exception as e:
                print(e)
        return datasource_arr

    def get_data(self, name, where=None, limit=None, offset=None):
        # @TODO Apply filter directly to postgres/mysql/clickhouse/etc...  when the datasource is of that type
        return get_sqlite_data(os.path.join(self.dir, name, 'datasource', 'sqlite.db'), where=where, limit=limit, offset=offset)

    def get_datasource(self, name):
        for ds in self.get_datasources():
            if ds['name'] == name:
                return ds
        return None

    def delete_datasource(self, name):
        data_sources = self.get_datasource(name)
        shutil.rmtree(os.path.join(self.dir, data_sources['name']))

    def save_datasource(self, name, source_type, source, file_path=None):
        if source_type == 'file' and (file_path is None):
            raise Exception('`file_path` argument required when source_type == "file"')

        for i in range(1, 1000):
            if name in [x['name'] for x in self.get_datasources()]:
                previous_index = i - 1
                name = name.replace(f'__{previous_index}__', '')
                name = f'{name}__{i}__'
            else:
                break

        ds_meta_dir = os.path.join(self.dir, name)
        os.mkdir(ds_meta_dir)

        ds_dir = os.path.join(ds_meta_dir, 'datasource')
        os.mkdir(ds_dir)

        if source_type == 'file':
            source = os.path.join(ds_dir, datasource_source)
            os.replace(file_path, source)
            ds = FileDS(source)
        elif source_type == 'clickhouse':
            ds = ClickhouseDS(source, user='default', password='201287')
        else:
            # This probably only happens for urls
            print('Create URL data source !')
            ds = FileDS(source)

        df = ds.df

        df_with_types = cast_df_columns_types(df, self.get_analysis(df)['data_analysis_v2'])
        create_sqlite_db(os.path.join(ds_dir, 'sqlite.db'), df_with_types)

        with open(os.path.join(ds_dir,'ds.pickle'), 'wb') as fp:
            pickle.dump(ds, fp)

        with open(os.path.join(ds_dir,'metadata.json'), 'w') as fp:
            json.dump({
                'name': name,
                'source_type': source_type,
                'source': source,
                'created_at': str(datetime.datetime.now()).split('.')[0],
                'updated_at': str(datetime.datetime.now()).split('.')[0],
                'row_count': len(df),
                'columns': [dict(name=x) for x in list(df.keys())]
            }, fp)

        return ds

    def get_datasource_obj(self, name):
        ds_meta_dir = os.path.join(self.dir, name)
        ds_dir = os.path.join(ds_meta_dir, 'datasource')
        try:
            #resource.setrlimit(resource.RLIMIT_STACK, [0x10000000, resource.RLIM_INFINITY])
            #sys.setrecursionlimit(0x100000)
            with open(os.path.join(ds_dir,'ds.pickle'), 'rb') as fp:
                ds = pickle.load(fp)
            print(ds)
            return ds
        except Exception as e:
            print(e)
            return None
