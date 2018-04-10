import sys, getopt
import numpy as np
sys.path.append('.')
import RTIMU
import os.path
import time
import math
import socket

# ========= global variables =================
prev_timestamp = time.time()*1000000
prev_vel = 0
prev_dis = 0
prev_result = np.array([[prev_dis], [prev_vel]])
skip_send = 10
skip_count = 0
offsetavg_sample_count = 300
offsetavg = 0

# ========== global imu class delaration ============= 
SETTINGS_FILE = "RTIMULib_090518_calib1"

print("Using settings file " + SETTINGS_FILE + ".ini")
if not os.path.exists(SETTINGS_FILE + ".ini"):
	print("Settings file does not exist, will be created")

s = RTIMU.Settings(SETTINGS_FILE)
imu = RTIMU.RTIMU(s)

if (not imu.IMUInit()):
    print("IMU Init Failed")
    sys.exit(1)
else:
    print("IMU Init Succeeded")

# =========== client _ server initialization =================
host = 'localhost'
port = 8000

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((host, port))


start_time = time.time()




#initialization
def init():
    global imu

    # this is a good time to set any fusion parameters
    print("IMU Name: " + imu.IMUName())
    
    imu.setSlerpPower(0.02)
    imu.setGyroEnable(True)
    imu.setAccelEnable(True)
    imu.setCompassEnable(True)

 
#main
def main():
    global imu, offsetavg
    sum_x = 0
    count = 0

    poll_interval = imu.IMUGetPollInterval()
    print("Recommended Poll Interval: %dmS\n" % poll_interval)



    # compute average on accel to obtain offset
    print("computing avg offset.... wait 5s")
    while True:

        if imu.IMURead():
            data = imu.getIMUData()
            raw_x, raw_y, raw_z = data['accel']
            pitch = data['fusionPose'][1]
            abs_x = raw_x*math.cos(pitch) + raw_z*math.sin(pitch)            

            # ignore initial dirty data from imu
            if (time.time() - start_time) > 2:
                if count < offsetavg_sample_count:
                    sum_x = sum_x + abs_x
                    count = count+1
                else:
                    break
        
            time.sleep(poll_interval*3.0/1000.0)
    
    offsetavg = sum_x/offsetavg_sample_count
    print "offsetavg is {}".format(offsetavg)
    print "start time {}, now {}".format(start_time, time.time())



    #run main
    while True:
        if imu.IMURead():
            #print "-------- Time stamp: {} ----------".format(time.time())

            # fusion data: means remove gravity on z-axis
            x, y, z = imu.getFusionData()
            #print("FUSION ACCEL:\t %f %f %f" % (x,y,z))

            data = imu.getIMUData()
            raw_x, raw_y, raw_z = data['accel']
            pitch = data['fusionPose'][1]
            abs_x = raw_x*math.cos(pitch) + raw_z*math.sin(pitch)
            
            #print("RAW ACCEL:\t %f %f %f" % (raw_x, raw_y, raw_z))
            #print("ABS ACCEL:\t {}".format(math.sqrt(raw_x*raw_x + raw_y*raw_y + raw_z*raw_z)))
            

            d, v, a = odometry_x(abs_x, data['timestamp'])
            sendToServer(d, v, a, data)

            time.sleep(poll_interval*1.0/1000.0)


# result = A_matrix * prev_result + B_matrix * accel
def odometry_x(accel, timestamp):
    global prev_result, prev_timestamp

    delta_t = timestamp - prev_timestamp

    #calib accel

    accel = accel - offsetavg
    computed_accel = accel* 9.8
    delta_t = float(delta_t)/1000000    #0.01s interval 100hz

    #elliminate noisy data during start
    if abs(accel) > 0 and (time.time() - start_time) > 8:
        A_matrix = np.array([[1, delta_t], [0,  1]])
        B_matrix = np.array([[0.5*delta_t*delta_t], [delta_t]])
        result = np.matmul( A_matrix, prev_result ) + computed_accel * B_matrix

        prev_result = result
    prev_timestamp = timestamp

    return prev_result[0], prev_result[1], computed_accel


#send data from client to server in 0.1 interval (according to skip_send)
def sendToServer(d, v, a, data):
    global skip_count

    if (skip_count == skip_send): 


        fusionPose = data["fusionPose"]
        raw_x, raw_y, raw_z = data['accel']
        print raw_x, (raw_z*math.sin(fusionPose[1]))
        print("RAW ACCEL:\t %f %f %f" % (raw_x, raw_y, raw_z))
        print("ABS ACCEL:\t {}".format(math.sqrt(raw_x*raw_x + raw_y*raw_y + raw_z*raw_z)))
        print("ROTATION:\t %f p: %f y: %f" % (math.degrees(fusionPose[0]), math.degrees(fusionPose[1]), math.degrees(fusionPose[2])))

        print("\t => d:{}, v:{}, a:{}".format(d, v, a))

        #send results to server
        client_socket.send(data)
        while client_socket.recv(2048) != "ack":
            print "Failed to connect to server!"
            print "waiting for ack"
            time.sleep(1)

        skip_count = 0
        
    else:
        skip_count = skip_count + 1
    


if __name__ == '__main__':
    try:
        # plt.pause(0.005)
        init()
        main()
    except KeyboardInterrupt:
        print("Shutting down...")
        sys.exit(0)
