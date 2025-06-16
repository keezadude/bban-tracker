# import the necessary packages
import datetime
import time  # required for VideoFileStream delay handling
from threading import Thread
import cv2
import pyrealsense2 as rs
import numpy as np
from pathlib import Path

class FPS:
	"""Simple frames-per-second counter.

	This utility class is used to benchmark how many frames are processed
	within a given time span.  Typical usage pattern::

		fps = FPS().start()
		while processing:
			...
			fps.update()
		fps.stop()
		print(fps.fps())

	The implementation purposefully keeps the public surface minimal so that
	it can be re-used in both the GUI (live FPS overlay) as well as in
	headless benchmarking scripts.
	"""

	def __init__(self):
		"""Create a new *stopped* counter with zero accumulated frames."""
		# store the start time, end time, and total number of frames that were
		# examined between the start and end intervals
		self._start = None
		self._end = None
		self._numFrames = 0
	def start(self):
		"""Begin a new timing interval.

		Returns:
			FPS: *self* – to enable fluent chaining (``FPS().start()``).
		"""
		# start the timer
		self._numFrames = 0
		self._start = datetime.datetime.now()
		return self
	def stop(self):
		"""Mark the end of the timing interval."""
		self._end = datetime.datetime.now()
	def update(self):
		"""Increment the internal frame counter by **one**.

		This should be called exactly once for every frame that has been
		fully processed or displayed.
		"""
		self._numFrames += 1
	def elapsed(self):
		"""Return the elapsed time (in **seconds**) between :py:meth:`start` and
		:py:meth:`stop`.  If :py:meth:`stop` has not been called yet the return
		value is undefined.
		"""
		return (self._end - self._start).total_seconds()
	def fps(self):
		"""Return the computed frames per second for the measured interval."""
		return self._numFrames / self.elapsed()
	
	def printFPS(self, interval: int = 10):
		"""Utility helper that prints the current FPS to *stdout* every *interval*
		processed frames.
		"""
		if self._numFrames > interval:
			self.stop()
			print(f"fps : {int(self.fps())}")
			self.start()

	

class WebcamVideoStream:
	"""Threaded wrapper around :pyclass:`cv2.VideoCapture`.

	Running the *read* loop in a separate thread significantly reduces frame
	latency compared to repeatedly calling ``VideoCapture.read()`` from the
	main GUI thread.  The implementation purposefully exposes only the
	operations required by the tracker so that the rest of the codebase can
	switch between *webcam* and *RealSense* seamlessly.
	"""

	def __init__(self, src: int = 0):
		"""Open the webcam located at **src** (device index)."""
		# initialize the video camera stream and read the first frame
		# from the stream
		self.stream = cv2.VideoCapture(src)
		# Compute frame delay based on the camera FPS (fallback to 30 FPS if unavailable)
		fps = self.stream.get(cv2.CAP_PROP_FPS)
		try:
			fps = float(fps) if fps and fps > 1e-3 else 30.0
		except Exception:
			fps = 30.0
		self._delay: float = 1.0 / fps
		(self.grabbed, self.frame) = self.stream.read()
		# initialize the variable used to indicate if the thread should
		# be stopped
		self.stopped = False
		self.wasFrameRead = False
		
        
	def start(self):
		"""Spawn the background thread and return *self* for chaining."""
		Thread(target=self.update, args=(), daemon=True).start()
		return self
	
	def update(self):
		"""Internal worker loop – do **not** call directly."""
		# keep looping infinitely until the thread is stopped
		while True:
			# if the thread indicator variable is set, stop the thread
			if self.stopped:
				return
			# otherwise, read the next frame from the stream
			(self.grabbed, self.frame) = self.stream.read()
			self.wasFrameRead = False
			time.sleep(self._delay)
			
	def read(self):
		"""Return the **latest** frame regardless of whether the consumer has
		consumed it before.  The image is converted to single-channel (gray)
		to match the IR output of RealSense for downstream compatibility.
		"""
		return cv2.cvtColor(self.frame, cv2.COLOR_BGR2GRAY)
	
	def readNext(self):
		"""Block until a *new* frame becomes available and return it in grayscale."""
		while True:
			if(not self.wasFrameRead):
				self.wasFrameRead = True
				return cv2.cvtColor(self.frame, cv2.COLOR_BGR2GRAY)
			
	def stop(self):
		"""Signal the background thread to terminate."""
		self.stopped = True

	def close(self):
		"""Gracefully stop the worker thread and release the underlying *VideoCapture*."""
		self.stop()
		self.stream.release()

    
class RealsenseStream:
	"""Non-blocking wrapper around an Intel RealSense *infra-red* stream.

	The tracker solely relies on the IR channel, therefore we configure the
	pipeline accordingly (single IR stream @ 640×360 @ 90 FPS to minimise
	USB bandwidth).  The class mirrors the public surface of
	:pyclass:`WebcamVideoStream` so that the rest of the application can
	interchange both sources transparently.
	
	Additionally, for depth processing, this class implements Intel's recommended
	post-processing filters chain to improve depth data quality:
	
	1. Decimation Filter - Reduces resolution for better performance
	2. Depth-to-Disparity Transform - Converts to disparity space for better filtering
	3. Spatial Filter - Edge-preserving smoothing to reduce noise while preserving edges
	4. Temporal Filter - Time-based smoothing to reduce flickering between frames
	5. Disparity-to-Depth Transform - Converts back to depth space
	6. Hole Filling Filter - Fills gaps in the depth data
	
	Each filter can be individually enabled/disabled through the API.
	"""

	def __init__(self):
		"""Initialise the RealSense pipeline and start a background fetch thread."""
		context = rs.context()
		sensor = context.sensors[0]
		# Disable the IR emitter – it introduces glare on most beystadium surfaces
		sensor.set_option(rs.option.emitter_enabled, 0.0)
		self.sensor = sensor  # <== retain reference for runtime control

		# Workaround: a pipeline must be started once before custom settings
		# (such as stream resolution) can be reliably applied when a camera is
		# plugged in for the first time.
		pipeline = rs.pipeline()
		pipeline.start()
		pipeline.stop()

		config = rs.config()
		# Stream 1: Infra-red (mono) channel – tracker uses this.
		config.enable_stream(rs.stream.infrared, 1, 640, 360, rs.format.y8, 90)
		# Stream 2: Depth stream for optional point-cloud debug view.
		config.enable_stream(rs.stream.depth, 640, 360, rs.format.z16, 30)

		pipeline.start(config)
		self.pipeline = pipeline
		
		# ---------------- Post-processing filters ---------------- #
		
		# --- Decimation Filter ---
		# Intelligently reduces the resolution of the depth image
		# Benefits: Reduces noise, speeds up processing, better for visualization
		self._filter_decimate_enabled = True
		self._filter_decimate = rs.decimation_filter()
		self._filter_decimate.set_option(rs.option.filter_magnitude, 2)  # 2× decimation (default)
		
		# --- Depth-to-Disparity & Disparity-to-Depth Transforms ---
		# Many filters work better in disparity space (1/distance) than in depth space
		# These transforms convert between the two domains
		self._filter_depth2disp = rs.disparity_transform(True)  # depth -> disparity
		self._filter_disp2depth = rs.disparity_transform(False) # disparity -> depth

		# --- Spatial Filter ---
		# Applies edge-preserving smoothing to reduce noise while preserving edges
		# Benefits: Smoother surfaces, reduced noise, preserved edges
		self._filter_spatial_enabled = True
		self._filter_spatial = rs.spatial_filter()
		self._filter_spatial.set_option(rs.option.filter_smooth_alpha, 0.5)  # Balance between current and filtered (0-1)
		self._filter_spatial.set_option(rs.option.filter_smooth_delta, 20)  # Depth difference threshold (>1)
		self._filter_spatial.set_option(rs.option.filter_magnitude, 2)      # Effect strength (1-5)
		self._filter_spatial.set_option(rs.option.holes_fill, 1)            # Hole filling mode (0-4)

		# --- Temporal Filter ---
		# Smooths depth values over time to reduce flickering
		# Benefits: Reduces temporal noise, stabilizes point clouds
		self._filter_temporal_enabled = True
		self._filter_temporal = rs.temporal_filter()
		self._filter_temporal.set_option(rs.option.filter_smooth_alpha, 0.4)  # Balance between current and history (0-1) 
		self._filter_temporal.set_option(rs.option.filter_smooth_delta, 20)   # Depth difference threshold (>1)
		self._filter_temporal.set_option(rs.option.holes_fill, 3)             # Hole filling mode (0-8)

		# --- Hole Filling Filter ---
		# Fills missing pixels (holes) in the depth image
		# Benefits: Provides complete depth information, reduces artifacts
		self._filter_hole_enabled = True
		self._filter_hole = rs.hole_filling_filter(1)  # Mode 1: Fill from nearest neighbors

		# Master toggle for all post-processing
		self._postproc_enabled = True  # can be toggled via set_postproc()

		frames = self.pipeline.wait_for_frames()
		self.ir_frame = frames.get_infrared_frame()
		self.depth_frame = frames.get_depth_frame()

		# Pointcloud helper (RealSense SDK)
		self._pc = rs.pointcloud()
		self._points = None  # rs.points
		
		# Get camera intrinsics for accurate 3D calculations
		self._depth_intrinsics = None
		if self.depth_frame:
			try:
				self._depth_intrinsics = self.depth_frame.profile.as_video_stream_profile().intrinsics
			except Exception:
				pass

		# Camera metadata
		self._camera_info = self._get_camera_info()

		self.stopped = False
		self.wasFrameRead = False
        
	def start(self):
		"""Spawn the background frame fetch thread."""
		Thread(target=self.update, args=(), daemon=True).start()
		return self
	
	def update(self):
		"""Internal worker loop that continuously fetches the latest IR frame."""
		while True:
			if self.stopped:
				return
			frames = self.pipeline.wait_for_frames()
			self.ir_frame = frames.get_infrared_frame()
			self.depth_frame = frames.get_depth_frame()
			
			# ---------------- Apply post-processing to depth ---------------- #
			if self._postproc_enabled and self.depth_frame:
				try:
					depth = self.depth_frame
					
					# Apply decimation filter (if enabled)
					if self._filter_decimate_enabled:
						depth = self._filter_decimate.process(depth)
					
					# Convert to disparity space for better filtering
					depth = self._filter_depth2disp.process(depth)
					
					# Apply spatial filter (if enabled)
					if self._filter_spatial_enabled:
						depth = self._filter_spatial.process(depth)
					
					# Apply temporal filter (if enabled)
					if self._filter_temporal_enabled:
						depth = self._filter_temporal.process(depth)
					
					# Convert back to depth space
					depth = self._filter_disp2depth.process(depth)
					
					# Apply hole filling (if enabled)
					if self._filter_hole_enabled:
						depth = self._filter_hole.process(depth)
					
					self.depth_frame = depth
					
					# Update depth intrinsics if changed
					try:
						self._depth_intrinsics = depth.profile.as_video_stream_profile().intrinsics
					except Exception:
						pass
						
				except Exception as e:
					# Fail silently – fall back to raw frame
					print(f"[RealsenseStream] Filter error: {e}")
					pass
					
			# Generate point-cloud vertices at full rate (but we may down-sample later in GUI)
			try:
				self._points = self._pc.calculate(self.depth_frame)
			except Exception:
				self._points = None
				
			self.wasFrameRead = False
			
	def read(self):
		"""Return the *latest* infrared frame (*rs.frame*)."""
		return self.ir_frame
	
	def readNext(self):
		"""Block until a **new** IR frame arrives and return it as a NumPy array."""
		while True:
			if(not self.wasFrameRead):
				self.wasFrameRead = True
				return np.asanyarray(self.ir_frame.get_data())
	
	def stop(self):
		"""Signal the background thread to terminate."""
		self.stopped = True
	
	def close(self):
		"""Gracefully stop the worker thread and *RealSense* pipeline."""
		self.stop()
		self.pipeline.stop()

	def set_option(self, option: rs.option, value: float):
		"""Safely set a RealSense sensor option at runtime (no-op on failure)."""
		try:
			self.sensor.set_option(option, value)
		except Exception as exc:
			print(f"[RealsenseStream] Failed to set option {option}: {exc}")

	def get_option(self, option: rs.option):
		"""Return the current value of a RealSense sensor option or **None** if unavailable."""
		try:
			return self.sensor.get_option(option)
		except Exception:
			return None

	# ---------------- Visual Preset Helpers ---------------- #
	def list_visual_presets(self):
		"""Return a list of tuples ``(value:int, name:str)`` of supported visual presets."""
		presets = []
		try:
			for i in range(int(rs.rs400_visual_preset.count)):  # pylint: disable=no-member
				try:
					name = rs.rs400_visual_preset(i).name  # type: ignore[attr-defined]
					# Some indices map to RESERVED/UNDEFINED – skip those that raise ValueError
					presets.append((i, name.replace("RS400_", "").replace("_", " ").title()))
				except Exception:
					continue
		except Exception:
			pass
		return presets

	def get_visual_preset(self) -> int | None:
		"""Return current visual preset value (int) or None on error."""
		return int(self.get_option(rs.option.visual_preset)) if self.sensor else None

	def set_visual_preset(self, value: int):
		"""Set the sensor's visual preset (best-effort)."""
		self.set_option(rs.option.visual_preset, float(value))

	# ---------------- Point-cloud enhanced API ---------------- #
	def get_pointcloud_vertices(self, max_points: int = 50000):
		"""Return an (N,3) float32 array of XYZ vertices in metres or None.

		The list is subsampled to *max_points* to keep rendering light-weight.
		"""
		if self._points is None:
			return None
		verts = np.asanyarray(self._points.get_vertices()).view(np.float32).reshape(-1, 3)
		if verts.size == 0:
			return None
		if verts.shape[0] > max_points:
			idx = np.random.choice(verts.shape[0], max_points, replace=False)
			verts = verts[idx]
		return verts
		
	def get_depth_at_pixel(self, x: int, y: int) -> float:
		"""Get depth value (in meters) at the specified pixel coordinates.
		
		Args:
			x: Pixel x-coordinate
			y: Pixel y-coordinate
			
		Returns:
			Depth in meters or 0.0 if unavailable
		"""
		if not self.depth_frame:
			return 0.0
		try:
			return self.depth_frame.get_distance(int(x), int(y))
		except Exception:
			return 0.0
			
	def deproject_pixel_to_point(self, x: int, y: int) -> tuple[float, float, float]:
		"""Convert a 2D pixel coordinate to a 3D point.
		
		Args:
			x: Pixel x-coordinate
			y: Pixel y-coordinate
			
		Returns:
			Tuple (x,y,z) in meters or (0,0,0) if unavailable
		"""
		if not self.depth_frame or not self._depth_intrinsics:
			return (0.0, 0.0, 0.0)
			
		try:
			depth = self.depth_frame.get_distance(int(x), int(y))
			if depth <= 0:
				return (0.0, 0.0, 0.0)
				
			point = rs.rs2_deproject_pixel_to_point(self._depth_intrinsics, [x, y], depth)
			return tuple(point)
		except Exception:
			return (0.0, 0.0, 0.0)
			
	def get_arena_dimensions(self) -> tuple[float, float, float]:
		"""Analyze the point cloud to estimate arena dimensions.
		
		Returns:
			Tuple (width, length, height) in meters or (0,0,0) if unavailable
		"""
		if self._points is None:
			return (0.0, 0.0, 0.0)
			
		try:
			verts = np.asanyarray(self._points.get_vertices()).view(np.float32).reshape(-1, 3)
			if verts.size == 0:
				return (0.0, 0.0, 0.0)
				
			# Filter out invalid points
			mask = ~np.isnan(verts).any(axis=1)
			verts = verts[mask]
			if verts.size == 0:
				return (0.0, 0.0, 0.0)
				
			# Calculate dimensions using the bounding box
			min_vals = np.min(verts, axis=0)
			max_vals = np.max(verts, axis=0)
			dimensions = max_vals - min_vals
			
			# Reorder to width, length, height (x, z, y in camera space)
			width = abs(dimensions[0])   # X dimension (width)
			length = abs(dimensions[2])  # Z dimension (length/depth)
			height = abs(dimensions[1])  # Y dimension (height)
			
			return (width, length, height)
		except Exception:
			return (0.0, 0.0, 0.0)
			
	def analyze_arena_floor(self) -> tuple[float, str]:
		"""Analyze the flatness of the arena floor.
		
		Returns:
			Tuple (flatness_score, description) where flatness_score is a value
			between 0.0 (very uneven) and 1.0 (perfectly flat). The description
			provides a human-readable assessment.
		"""
		if self._points is None:
			return (0.0, "No point cloud data available")
			
		try:
			verts = np.asanyarray(self._points.get_vertices()).view(np.float32).reshape(-1, 3)
			if verts.size == 0:
				return (0.0, "No valid points in cloud")
				
			# Filter out invalid points and points too far away
			mask = ~np.isnan(verts).any(axis=1)
			verts = verts[mask]
			if verts.size == 0:
				return (0.0, "No valid points after filtering")
				
			# Simple flatness analysis: calculate the standard deviation of Y values
			# after removing extreme outliers
			y_values = verts[:, 1]
			q1, q3 = np.percentile(y_values, [25, 75])
			iqr = q3 - q1
			lower_bound = q1 - 1.5 * iqr
			upper_bound = q3 + 1.5 * iqr
			filtered_y = y_values[(y_values >= lower_bound) & (y_values <= upper_bound)]
			
			if filtered_y.size < 10:
				return (0.0, "Too few points for analysis")
				
			std_dev = np.std(filtered_y)
			
			# Convert to flatness score (0.0 to 1.0)
			# A standard deviation of 0.0 means perfectly flat
			# A standard deviation of 0.01 (1cm) or more is considered very uneven
			flatness = max(0.0, min(1.0, 1.0 - std_dev * 100))
			
			# Generate description
			if flatness > 0.95:
				description = "Excellent - Very flat surface"
			elif flatness > 0.85:
				description = "Good - Mostly flat surface"
			elif flatness > 0.7:
				description = "Fair - Some unevenness detected"
			else:
				description = "Poor - Surface is uneven"
				
			return (flatness, description)
		except Exception as e:
			return (0.0, f"Analysis error: {str(e)}")

	# ---------------- Camera information ---------------- #
	def _get_camera_info(self) -> dict:
		"""Get detailed camera information.
		
		Returns:
			Dictionary containing camera metadata
		"""
		info = {
			"name": "Intel RealSense",
			"model": "Unknown",
			"serial": "Unknown",
			"firmware": "Unknown",
		}
		
		try:
			if not self.pipeline:
				return info
				
			# Get device info
			profile = self.pipeline.get_active_profile()
			dev = profile.get_device()
			
			# Extract information
			info["model"] = dev.get_info(rs.camera_info.name) if dev.supports(rs.camera_info.name) else "Unknown"
			info["serial"] = dev.get_info(rs.camera_info.serial_number) if dev.supports(rs.camera_info.serial_number) else "Unknown"
			info["firmware"] = dev.get_info(rs.camera_info.firmware_version) if dev.supports(rs.camera_info.firmware_version) else "Unknown"
		except Exception:
			pass
			
		return info
		
	def get_camera_info(self) -> dict:
		"""Return camera metadata dictionary.
		
		Returns:
			Dictionary with camera make, model, serial, and firmware info
		"""
		return self._camera_info.copy()
			
	# ---------------- Filter control API ---------------- #
	def set_postprocessing_enabled(self, enable: bool = True):
		"""Enable or disable all depth post-processing filters.
		
		Args:
			enable: True to enable all filters, False to disable all processing
		"""
		self._postproc_enabled = bool(enable)
		
	def set_decimation_enabled(self, enable: bool = True):
		"""Enable or disable the decimation filter.
		
		The decimation filter reduces the depth frame resolution through
		intelligent subsampling. This improves performance and can reduce
		noise at the cost of detail.
		
		Args:
			enable: True to enable the filter, False to disable
		"""
		self._filter_decimate_enabled = bool(enable)
		
	def set_spatial_filter_enabled(self, enable: bool = True):
		"""Enable or disable the spatial filter.
		
		The spatial filter performs edge-preserving smoothing, which reduces
		noise on flat surfaces while maintaining sharp edges and details.
		
		Args:
			enable: True to enable the filter, False to disable
		"""
		self._filter_spatial_enabled = bool(enable)
		
	def set_temporal_filter_enabled(self, enable: bool = True):
		"""Enable or disable the temporal filter.
		
		The temporal filter reduces temporal noise (flickering between frames)
		by averaging depth values over time. This stabilizes the tracking.
		
		Args:
			enable: True to enable the filter, False to disable
		"""
		self._filter_temporal_enabled = bool(enable)
		
	def set_hole_filling_enabled(self, enable: bool = True):
		"""Enable or disable the hole filling filter.
		
		The hole filling filter fills gaps in the depth data by interpolating
		from neighboring valid pixels. This can improve tracking by reducing
		missing regions.
		
		Args:
			enable: True to enable the filter, False to disable
		"""
		self._filter_hole_enabled = bool(enable)
		
	def set_decimation_magnitude(self, value: int):
		"""Set the decimation filter subsampling factor (1-8).
		
		Higher values produce lower resolution but faster processing.
		
		Args:
			value: Decimation magnitude (1-8), typically 2-4
		"""
		try:
			self._filter_decimate.set_option(rs.option.filter_magnitude, float(max(1, min(8, value))))
		except Exception as e:
			print(f"[RealsenseStream] Failed to set decimation magnitude: {e}")
		
	def set_spatial_filter_params(self, smooth_alpha: float, smooth_delta: float, magnitude: float = 2.0):
		"""Configure the spatial filter parameters.
		
		Args:
			smooth_alpha: Weight of the current pixel vs. filtered (0.0-1.0)
			smooth_delta: Depth difference threshold in mm (> 1.0)
			magnitude: Filter effect strength (1.0-5.0)
		"""
		try:
			self._filter_spatial.set_option(rs.option.filter_smooth_alpha, float(max(0.0, min(1.0, smooth_alpha))))
			self._filter_spatial.set_option(rs.option.filter_smooth_delta, float(max(1.0, smooth_delta)))
			self._filter_spatial.set_option(rs.option.filter_magnitude, float(max(1.0, min(5.0, magnitude))))
		except Exception as e:
			print(f"[RealsenseStream] Failed to set spatial filter params: {e}")
		
	def set_temporal_filter_params(self, smooth_alpha: float, smooth_delta: float):
		"""Configure the temporal filter parameters.
		
		Args:
			smooth_alpha: Weight of the current frame vs. history (0.0-1.0)
			smooth_delta: Depth difference threshold in mm (> 1.0)
		"""
		try:
			self._filter_temporal.set_option(rs.option.filter_smooth_alpha, float(max(0.0, min(1.0, smooth_alpha))))
			self._filter_temporal.set_option(rs.option.filter_smooth_delta, float(max(1.0, smooth_delta)))
		except Exception as e:
			print(f"[RealsenseStream] Failed to set temporal filter params: {e}")
		
	def set_hole_filling_mode(self, mode: int):
		"""Set the hole filling strategy (0-4).
		
		Different modes use different techniques to fill holes:
		- 0: Do not fill
		- 1: Fill from nearest neighbors (default)
		- 2: Farthest from around the hole
		- 3: Fill from nearest lower pixel
		- 4: Fill from nearest valid pixel
		
		Args:
			mode: Hole filling mode (0-4)
		"""
		try:
			# Create new filter with specified mode
			self._filter_hole = rs.hole_filling_filter(max(0, min(4, mode)))
		except Exception as e:
			print(f"[RealsenseStream] Failed to set hole filling mode: {e}")
	
	def get_filter_status(self) -> dict:
		"""Return the current status of all post-processing filters.
		
		Returns:
			Dictionary with current filter settings
		"""
		return {
			"master_enabled": self._postproc_enabled,
			"decimation": {
				"enabled": self._filter_decimate_enabled,
				"magnitude": int(self._filter_decimate.get_option(rs.option.filter_magnitude))
			},
			"spatial": {
				"enabled": self._filter_spatial_enabled,
				"smooth_alpha": float(self._filter_spatial.get_option(rs.option.filter_smooth_alpha)),
				"smooth_delta": float(self._filter_spatial.get_option(rs.option.filter_smooth_delta)),
				"magnitude": float(self._filter_spatial.get_option(rs.option.filter_magnitude))
			},
			"temporal": {
				"enabled": self._filter_temporal_enabled,
				"smooth_alpha": float(self._filter_temporal.get_option(rs.option.filter_smooth_alpha)),
				"smooth_delta": float(self._filter_temporal.get_option(rs.option.filter_smooth_delta)),
			},
			"hole_filling": {
				"enabled": self._filter_hole_enabled
			}
		}

# ---------------------------------------------------------------------------
# VideoFileStream – threaded wrapper around cv2.VideoCapture for file playback
# ---------------------------------------------------------------------------

class VideoFileStream:
	"""Threaded video file reader that mimics WebcamVideoStream API.

	The class reads frames from a video file path in a background thread to
	provide non-blocking access. When the end of file is reached it loops back
	to the first frame (useful for continuous demos in kiosk setups).
	"""

	def __init__(self, path: str):
		if not Path(path).exists():
			raise FileNotFoundError(path)
		self.stream = cv2.VideoCapture(path)
		if not self.stream.isOpened():
			raise RuntimeError(f"Unable to open video: {path}")

		self.fps = self.stream.get(cv2.CAP_PROP_FPS) or 30
		self._delay = 1.0 / self.fps

		(self.grabbed, frame) = self.stream.read()
		if frame is None:
			raise RuntimeError("Video contains no frames")
		self.frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

		self.stopped = False
		self.wasFrameRead = False

	def start(self):
		Thread(target=self.update, args=(), daemon=True).start()
		return self

	def update(self):
		while True:
			if self.stopped:
				return
			(self.grabbed, frame) = self.stream.read()
			if not self.grabbed:
				# Loop: rewind to first frame
				self.stream.set(cv2.CAP_PROP_POS_FRAMES, 0)
				continue
			self.frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
			self.wasFrameRead = False
			time.sleep(self._delay)

	def read(self):
		return self.frame

	def readNext(self):
		while True:
			if not self.wasFrameRead:
				self.wasFrameRead = True
				return self.frame

	def stop(self):
		self.stopped = True

	def close(self):
		self.stop()
		self.stream.release()