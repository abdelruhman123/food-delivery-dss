import pandas as pd
from sqlalchemy import create_engine, text
import os

def ingest_delivery_data():
    engine = create_engine('postgresql://root:root@localhost:5555/food_delivery')
    csv_name = 'data/raw/deliveries.csv'
    
    # 3. (Chunks)
    df_iter = pd.read_csv(csv_name, iterator=True, chunksize=10000)
    df = next(df_iter)

    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE raw_deliveries CASCADE;"))

    df.to_sql(name='raw_deliveries', con=engine, if_exists='append', index=False)
    print("first 10k raws ")

    while True:
        try:
            df = next(df_iter)
            df.to_sql(name='raw_deliveries', con=engine, if_exists='append', index=False)
            print('fist step of ingestion done')
        except StopIteration:
            print('all of data in postgres')
            break
            
    return {"status": "success", "rows": 10000} 

if __name__ == "__main__":
    ingest_delivery_data()