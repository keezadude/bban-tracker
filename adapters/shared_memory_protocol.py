"""
Shared memory protocol definitions for BBAN-Tracker to Unity client communication.

This module defines the binary protocol and data structures used for 
high-performance inter-process communication with the immutable Unity client.
"""

import struct
import time
import zlib
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import IntEnum

import msgpack


class ProtocolVersion(IntEnum):
    """Protocol version constants."""
    V1_0 = 1


class CommandType(IntEnum):
    """Command types from Unity client to tracker."""
    CALIBRATE = 1
    THRESHOLD_ADJUST = 2
    CONFIG_CHANGE = 3
    HEARTBEAT = 4
    SHUTDOWN = 5


# Protocol Constants
MAGIC_NUMBER = 0xBEBA2024
HEADER_SIZE = 64
MAX_PAYLOAD_SIZE = 1024 * 1024  # 1MB max payload
DEFAULT_SHARED_MEMORY_SIZE = 2 * 1024 * 1024  # 2MB total


@dataclass(frozen=True)
class ProjectionConfig:
    """Projection configuration for Unity client."""
    width: int
    height: int
    display_index: int = 0
    fullscreen: bool = True
    refresh_rate: int = 60
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'width': self.width,
            'height': self.height,
            'display_index': self.display_index,
            'fullscreen': self.fullscreen,
            'refresh_rate': self.refresh_rate
        }


@dataclass(frozen=True)
class BeyData:
    """Immutable Beyblade tracking data for shared memory."""
    id: int
    pos_x: float
    pos_y: float
    velocity_x: float
    velocity_y: float
    raw_velocity_x: float
    raw_velocity_y: float
    acceleration_x: float
    acceleration_y: float
    width: int
    height: int
    frame: int
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'id': self.id,
            'pos_x': self.pos_x,
            'pos_y': self.pos_y,
            'velocity_x': self.velocity_x,
            'velocity_y': self.velocity_y,
            'raw_velocity_x': self.raw_velocity_x,
            'raw_velocity_y': self.raw_velocity_y,
            'acceleration_x': self.acceleration_x,
            'acceleration_y': self.acceleration_y,
            'width': self.width,
            'height': self.height,
            'frame': self.frame
        }


@dataclass(frozen=True)
class HitData:
    """Immutable collision data for shared memory."""
    pos_x: float
    pos_y: float
    width: int
    height: int
    bey_id_1: int
    bey_id_2: int
    is_new_hit: bool
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'pos_x': self.pos_x,
            'pos_y': self.pos_y,
            'width': self.width,
            'height': self.height,
            'bey_id_1': self.bey_id_1,
            'bey_id_2': self.bey_id_2,
            'is_new_hit': self.is_new_hit
        }


@dataclass(frozen=True)
class SharedMemoryFrame:
    """Complete frame data for Unity client communication."""
    frame_id: int
    timestamp: float
    beys: List[BeyData]
    hits: List[HitData]
    projection_config: Optional[ProjectionConfig] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'frame_id': self.frame_id,
            'timestamp': self.timestamp,
            'beys': [bey.to_dict() for bey in self.beys],
            'hits': [hit.to_dict() for hit in self.hits],
            'projection_config': self.projection_config.to_dict() if self.projection_config else None
        }


@dataclass
class UnityCommand:
    """Command from Unity client to tracker."""
    command_type: CommandType
    parameters: Dict[str, Any]
    timestamp: float = field(default_factory=time.perf_counter)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'command_type': int(self.command_type),
            'parameters': self.parameters,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'UnityCommand':
        """Create from dictionary after deserialization."""
        return cls(
            command_type=CommandType(data['command_type']),
            parameters=data['parameters'],
            timestamp=data['timestamp']
        )


class SharedMemoryHeader:
    """Binary header for shared memory protocol."""
    
    # Header format: magic(I) + version(I) + frame_counter(Q) + data_size(Q) + checksum(I) + reserved(28s)
    FORMAT = '<IIQQI28s'
    
    def __init__(self, frame_counter: int = 0, data_size: int = 0, checksum: int = 0):
        self.magic_number = MAGIC_NUMBER
        self.version = ProtocolVersion.V1_0
        self.frame_counter = frame_counter
        self.data_size = data_size
        self.checksum = checksum
        self.reserved = b'\x00' * 28
    
    def pack(self) -> bytes:
        """Pack header into binary format."""
        return struct.pack(
            self.FORMAT,
            self.magic_number,
            self.version,
            self.frame_counter,
            self.data_size,
            self.checksum,
            self.reserved
        )
    
    @classmethod
    def unpack(cls, data: bytes) -> 'SharedMemoryHeader':
        """Unpack header from binary format."""
        if len(data) < HEADER_SIZE:
            raise ValueError(f"Header data too short: {len(data)} < {HEADER_SIZE}")
        
        values = struct.unpack(cls.FORMAT, data[:HEADER_SIZE])
        header = cls()
        header.magic_number = values[0]
        header.version = values[1]
        header.frame_counter = values[2]
        header.data_size = values[3]
        header.checksum = values[4]
        header.reserved = values[5]
        
        return header
    
    def validate(self) -> bool:
        """Validate header integrity."""
        return (
            self.magic_number == MAGIC_NUMBER and
            self.version == ProtocolVersion.V1_0 and
            self.data_size <= MAX_PAYLOAD_SIZE
        )


class ProtocolSerializer:
    """High-performance serializer for shared memory protocol."""
    
    @staticmethod
    def serialize_frame(frame: SharedMemoryFrame) -> bytes:
        """Serialize frame data using MessagePack."""
        try:
            data_dict = frame.to_dict()
            return msgpack.packb(data_dict, use_bin_type=True)
        except Exception as e:
            raise RuntimeError(f"Failed to serialize frame: {e}")
    
    @staticmethod
    def deserialize_frame(data: bytes) -> SharedMemoryFrame:
        """Deserialize frame data from MessagePack."""
        try:
            data_dict = msgpack.unpackb(data, raw=False)
            
            # Reconstruct BeyData objects
            beys = [
                BeyData(
                    id=bey['id'],
                    pos_x=bey['pos_x'],
                    pos_y=bey['pos_y'],
                    velocity_x=bey['velocity_x'],
                    velocity_y=bey['velocity_y'],
                    raw_velocity_x=bey['raw_velocity_x'],
                    raw_velocity_y=bey['raw_velocity_y'],
                    acceleration_x=bey['acceleration_x'],
                    acceleration_y=bey['acceleration_y'],
                    width=bey['width'],
                    height=bey['height'],
                    frame=bey['frame']
                )
                for bey in data_dict['beys']
            ]
            
            # Reconstruct HitData objects
            hits = [
                HitData(
                    pos_x=hit['pos_x'],
                    pos_y=hit['pos_y'],
                    width=hit['width'],
                    height=hit['height'],
                    bey_id_1=hit['bey_id_1'],
                    bey_id_2=hit['bey_id_2'],
                    is_new_hit=hit['is_new_hit']
                )
                for hit in data_dict['hits']
            ]
            
            # Reconstruct ProjectionConfig if present
            projection_config = None
            if data_dict['projection_config']:
                config_dict = data_dict['projection_config']
                projection_config = ProjectionConfig(
                    width=config_dict['width'],
                    height=config_dict['height'],
                    display_index=config_dict.get('display_index', 0),
                    fullscreen=config_dict.get('fullscreen', True),
                    refresh_rate=config_dict.get('refresh_rate', 60)
                )
            
            return SharedMemoryFrame(
                frame_id=data_dict['frame_id'],
                timestamp=data_dict['timestamp'],
                beys=beys,
                hits=hits,
                projection_config=projection_config
            )
        except Exception as e:
            raise RuntimeError(f"Failed to deserialize frame: {e}")
    
    @staticmethod
    def serialize_command(command: UnityCommand) -> bytes:
        """Serialize Unity command using MessagePack."""
        try:
            data_dict = command.to_dict()
            return msgpack.packb(data_dict, use_bin_type=True)
        except Exception as e:
            raise RuntimeError(f"Failed to serialize command: {e}")
    
    @staticmethod
    def deserialize_command(data: bytes) -> UnityCommand:
        """Deserialize Unity command from MessagePack."""
        try:
            data_dict = msgpack.unpackb(data, raw=False)
            return UnityCommand.from_dict(data_dict)
        except Exception as e:
            raise RuntimeError(f"Failed to deserialize command: {e}")
    
    @staticmethod
    def calculate_checksum(data: bytes) -> int:
        """Calculate CRC32 checksum for data integrity."""
        return zlib.crc32(data) & 0xFFFFFFFF


def create_shared_memory_frame(
    frame_id: int,
    beys: List[Any],  # From core.events.BeyData
    hits: List[Any],  # From core.events.HitData
    projection_config: Optional[ProjectionConfig] = None
) -> SharedMemoryFrame:
    """
    Create SharedMemoryFrame from core event data.
    
    This function converts the internal event data structures to the
    shared memory protocol format.
    """
    # Convert core BeyData to protocol BeyData
    protocol_beys = []
    for bey in beys:
        protocol_beys.append(BeyData(
            id=bey.id,
            pos_x=float(bey.pos[0]),
            pos_y=float(bey.pos[1]),
            velocity_x=bey.velocity[0],
            velocity_y=bey.velocity[1],
            raw_velocity_x=bey.raw_velocity[0],
            raw_velocity_y=bey.raw_velocity[1],
            acceleration_x=bey.acceleration[0],
            acceleration_y=bey.acceleration[1],
            width=bey.shape[0],
            height=bey.shape[1],
            frame=bey.frame
        ))
    
    # Convert core HitData to protocol HitData
    protocol_hits = []
    for hit in hits:
        protocol_hits.append(HitData(
            pos_x=float(hit.pos[0]),
            pos_y=float(hit.pos[1]),
            width=hit.shape[0],
            height=hit.shape[1],
            bey_id_1=hit.bey_ids[0],
            bey_id_2=hit.bey_ids[1],
            is_new_hit=hit.is_new_hit
        ))
    
    return SharedMemoryFrame(
        frame_id=frame_id,
        timestamp=time.perf_counter(),
        beys=protocol_beys,
        hits=protocol_hits,
        projection_config=projection_config
    ) 