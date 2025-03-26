# import the necessary packages
import datetime
from threading import Thread
import cv2
import pyrealsense2 as rs
import numpy as np

class FPS:
	def __init__(self):
		# store the start time, end time, and total number of frames
		# that were examined between the start and end intervals
		self._start = None
		self._end = None
		self._numFrames = 0
	def start(self):
		# start the timer
		self._numFrames = 0
		self._start = datetime.datetime.now()
		return self
	def stop(self):
		# stop the timer
		self._end = datetime.datetime.now()
	def update(self):
		# increment the total number of frames examined during the
		# start and end intervals
		self._numFrames += 1
	def elapsed(self):
		# return the total number of seconds between the start and
		# end interval
		return (self._end - self._start).total_seconds()
	def fps(self):
		# compute the (approximate) frames per second
		return self._numFrames / self.elapsed()
	
	def printFPS(self, interval = 10):
		if(self._numFrames > interval):
			self.stop()
			print(f"fps : {int(self.fps())}")
			self.start()

	

class WebcamVideoStream:
	def __init__(self, src=0):
		# initialize the video camera stream and read the first frame
		# from the stream
		self.stream = cv2.VideoCapture(src)
		(self.grabbed, self.frame) = self.stream.read()
		# initialize the variable used to indicate if the thread should
		# be stopped
		self.stopped = False
		self.wasFrameRead = False
		
        
	def start(self):
		# start the thread to read frames from the video stream
		Thread(target=self.update, args=()).start()
		return self
	
	def update(self):
		# keep looping infinitely until the thread is stopped
		while True:
			# if the thread indicator variable is set, stop the thread
			if self.stopped:
				return
			# otherwise, read the next frame from the stream
			(self.grabbed, self.frame) = self.stream.read()
			self.wasFrameRead = False
			
	def read(self):
		# return the frame most recently read
		return cv2.cvtColor(self.frame, cv2.COLOR_BGR2GRAY)
	
	def readNext(self):
		while True:
			if(not self.wasFrameRead):
				self.wasFrameRead = True
				return cv2.cvtColor(self.frame, cv2.COLOR_BGR2GRAY)
			
	def stop(self):
		# indicate that the thread should be stopped
		self.stopped = True

	def close(self):
		self.stop()
		self.stream.release()

    
class RealsenseStream:
	def __init__(self):
		context = rs.context()
		sensor = context.sensors[0]
		sensor.set_option(rs.option.emitter_enabled, 0.0)

		# pipelineを一度start()しないと最初の接続時に設定が反映されない
		pipeline = rs.pipeline()
		pipeline.start()
		pipeline.stop()

		config = rs.config()
		config.enable_stream(rs.stream.infrared, 1, 640, 360, rs.format.y8, 90)

		pipeline.start(config)
		self.pipeline = pipeline
		
		frames = self.pipeline.wait_for_frames()
		self.ir_frame = frames.get_infrared_frame()

		self.stopped = False
		self.wasFrameRead = False
        
	def start(self):
		Thread(target=self.update, args=()).start()
		return self
	
	def update(self):
		while True:
			if self.stopped:
				return
			frames = self.pipeline.wait_for_frames()
			self.ir_frame = frames.get_infrared_frame()
			self.wasFrameRead = False
			
	def read(self):
		# return the frame most recently read
		return self.ir_frame
	
	def readNext(self):
		while True:
			if(not self.wasFrameRead):
				self.wasFrameRead = True
				return np.asanyarray(self.ir_frame.get_data())
	
	def stop(self):
		# indicate that the thread should be stopped
		self.stopped = True
	
	def close(self):
		self.stop()
		self.pipeline.stop()