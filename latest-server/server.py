from flask import Flask, request, jsonify, make_response
from influxdb import InfluxDBClient
from werkzeug.security import generate_password_hash, check_password_hash
import uuid 
import jwt
import json
from datetime import datetime, timedelta
from functools import wraps
import os
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__) 

app.config['SECRET_KEY']='Th1s1ss3cr3t'

database_name = 'DriveS_v2'

client = InfluxDBClient('localhost', 8086, 'root', 'root', database_name)
client.create_database(database_name)

"""
Database: DriveS_v2
Measurement: usertable
Tag: username
Field: password_hash, public_id

Measurement: data
Tag: uuid, launch, public_id
Field: velocity, acceleration, gyroscope, latitude, longitude

API:
Route: /register
Methods: ['GET', 'POST']
Token: not required
Header:
    Authorization: <type> <credentials>
* Explanation of header authorization:
    it contains the encoded username-password pair,
    Swift provides API for this commonly used header


Route: /login
Methods: ['GET', 'POST']
Token: not required
Header:
    Authorization: <type> <credentials>

Route: /upload
Methods: ['POST']
Token: required
Header: 
    x-access-tokens: <token>
Body:
    * Same as the original version, i.e.
    * Format of request in Swift
    * let body = ["UserID":uuid,
    *             "LaunchTimestamp":LAUNCH_TIMESTAMP,
    *             "Data":uploadBuffer 
    *            ] as Dictionary<String, String>
    * Format of each line in Data in Swift
    * uploadBuffer += (Date().GetTime+",\(velocity),\(accCal[1]),\(gyroCal[2]),\(latitude),\(longitude),\n")
"""


def token_required(f):  
    @wraps(f)  
    def decorator(*args, **kwargs):

        token = None 

        if 'x-access-tokens' in request.headers:  
            token = request.headers['x-access-tokens'] 

        if not token:  
            return jsonify({'message': 'a valid token is missing'}), 400

        data = jwt.decode(token, 
                            key=app.config['SECRET_KEY'],
                            algorithms="HS256") 
        try:  
            public_id = data['public_id']
            results = client.query("SELECT * from usertable where public_id='{}';".format(public_id))
            points = results.get_points()
            size = sum(1 for point in points)
            if size == 0:
                return jsonify({'message': 'do not find user'}), 400
            if size > 1:
                return jsonify({'message': 'multiple user with same public_id found'}), 400
        except:  
            return jsonify({'message': 'token is invalid'}), 400

        return f(public_id, *args,  **kwargs)  

    return decorator 
        

@app.route('/register', methods=['GET', 'POST'])
def signup_user():  
    
    auth = request.authorization   

    if not auth or not auth.username or not auth.password:  
        return make_response('could not verify', 401, {'WWW.Authentication': 'Basic realm: "login required"'})    

    username = auth.username
    results = client.query("SELECT * from usertable where username='{}';".format(username))
    points = results.get_points()
    size = sum(1 for point in points)
    if size > 0:
        return jsonify({'message': 'user name is registered'}), 400

    password_hash = generate_password_hash(auth.password, method='sha256')

    public_id = str(uuid.uuid4())

    json_body = [
        {
            "measurement": "usertable",
            "time": datetime.utcnow().isoformat("T") + "Z",
            "tags": {
                "username": username
            },
            "fields": {
                "password_hash": password_hash,
                "public_id": public_id
            }
        }
    ]
    client.write_points(json_body)

    return jsonify({'message': 'registered successfully'}), 200


@app.route('/login', methods=['GET', 'POST'])  
def login_user(): 

    auth = request.authorization   

    if not auth or not auth.username or not auth.password:  
        return make_response('could not verify', 401, {'WWW.Authentication': 'Basic realm: "login required"'})    

    username = auth.username
    results = client.query("SELECT * from usertable where username='{}';".format(username))
    points = results.get_points(tags={'username': username})
    size = 0
    for _point in points:
        size += 1
        if size == 1:
            point = _point
    if size == 0:
        return jsonify({'message': 'user not found'}), 400

    password_hash = point['password_hash']
    public_id = point['public_id']
        
    if check_password_hash(password_hash, auth.password):  
        token = jwt.encode({'public_id': public_id, 'exp' : datetime.utcnow() + timedelta(days=365)}, 
                           app.config['SECRET_KEY'],
                           algorithm="HS256")  
        return jsonify({'token' : token}), 200

    return make_response('could not verify',  401, {'WWW-Authentication': 'Basic realm: "login required"'})


@app.route('/upload', methods=['POST'])
@token_required
def create_record(public_id):
    '''
    * Format of request in Swift
    * let body = ["UserID":uuid,
    *             "LaunchTimestamp":LAUNCH_TIMESTAMP,
    *             "Data":uploadBuffer 
    *            ] as Dictionary<String, String>
    * Format of each line in Data in Swift
    * uploadBuffer += (Date().GetTime+",\(velocity),\(accCal[1]),\(gyroCal[2]),\(latitude),\(longitude),\n")
    '''
    # data = request.get_json() 
    data = json.loads(request.get_data(as_text=True))
    uuid = data['UserID']
    LaunchTimestamp = data['LaunchTimestamp']
    Data = data['Data']

    Data = Data.splitlines()
    for line in Data:
        line = line.split(',')
        # print(line)
        body = [
            {
                "measurement": "data",
                "time": line[0],
                "tags":{
                    "uuid": uuid,
                    "launch": LaunchTimestamp,
                    "public_id": public_id
                },
                "fields": {
                    "velocity":float(line[1]),
                    "acceleration":float(line[2]),
                    "gyroscope":float(line[3]),
                    "latitude":float(line[4]),
                    "longitude":float(line[5])
                }
            }
        ]
        client.write_points(body)

    return jsonify({'message' : 'package received'}), 200


if  __name__ == '__main__':  
     app.run(host='0.0.0.0', port=5000, debug=True)