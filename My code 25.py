# ============================================
# MGS V FMDL IMPORTER FOR BLENDER - COMPLETE
# ============================================
# Paste this in Blender's Scripting tab and run

import bpy
import bmesh
import struct
import os
from pathlib import Path
from mathutils import Vector, Matrix, Quaternion
import xml.etree.ElementTree as ET

# ============================================
# SECTION 1: USER CONFIGURATION (EDIT THESE PATHS)
# ============================================

FMDL_PATH = r"F:\\Game\\! Extracted File From GAMES\\Extract MGS V TPP\\MGS V TPP FileMonolith.v0.4.0 and Archive Unpacker\\Assets\\tpp\\chara\\ddg\\Scenes\\ddg0_main3_def.fmdl"
TEXTURE_FOLDER = r"F:\\Game\\! Extracted File From GAMES\\Extract MGS V TPP\\MGS V TPP FileMonolith.v0.4.0 and Mass Texture ( just extract .ftex and .ftexs files to .dds)"
DICTIONARY_FOLDER = r"C:\\Users\\Ali\\Desktop\\MGS Vtpp blender\\444\\dictionary"
DLL_FOLDER = r"C:\\Users\\Ali\\Desktop\\MGS Vtpp blender\\444\\references"  # CityHash.dll و System.Half.dll

# SETTINGS
AABB_MODE = 'all'  # 'all' = all AABBs, 'important' = root bones only, 'none' = skip
CREATE_AABBS = True  # Set to False to disable AABB creation

# ============================================
# SECTION 1.5: IMPORTS & CONSTANTS
# ============================================

FMDL_MAGIC = b"FMDL"
VERSION_GZ = 0x20140610
VERSION_TPP = 0x20150211

# Vertex format element usage enums (corrected duplicates)
MESH_BUFFER_FORMAT_ELEMENT_USAGE = {
    0: 'POSITION',
    1: 'BONE_WEIGHT0',
    2: 'NORMAL',
    3: 'COLOR',
    4: 'BONE_INDEX0',      # Fixed: was BONE_INDEX1
    5: 'BONE_WEIGHT1',
    6: 'BONE_INDEX1',      # Fixed: was BONE_INDEX0  
    7: 'BONE_INDEX2',      # Fixed: was duplicate BONE_INDEX0
    8: 'UV0',
    9: 'UV1',
    10: 'UV2',
    11: 'UV3',
    12: 'BONE_WEIGHT2',    # Fixed: was duplicate BONE_WEIGHT1
    13: 'BONE_INDEX3',     # Fixed: was duplicate BONE_INDEX1
    14: 'TANGENT',
    15: 'BINORMAL',
}

# Vertex format element type enums (corrected/reordered)
MESH_BUFFER_FORMAT_ELEMENT_TYPE = {
    0: 'R32G32B32_FLOAT',     # Position (fixed)
    1: 'R8G8B8A8_UNORM',      # Weights (fixed)
    2: 'R16G16B16A16_FLOAT',  # Normal
    3: 'R8G8B8A8_UNORM',      # Color
    4: 'R8G8B8A8_UINT',       # Bone Indices
    5: 'R8G8B8A8_UNORM',      # Additional Weights
    6: 'R8G8B8A8_UINT',       # Additional Indices
    7: 'R16G16_FLOAT',        # UVs
    8: 'R8G8B8A8_UNORM',      # Color/Weights
    9: 'R8G8B8A8_UINT',       # Bone Indices
    10: 'R16_FLOAT',
    11: 'R16G32_FLOAT',
    12: 'R16G32B32_FLOAT',
    13: 'R16G32B32A32_FLOAT',
    14: 'R32G32B32_FLOAT',    # Tangent
    15: 'R32G32B32_FLOAT',    # Binormal
}

# Texture role to suffix mapping (PES/MGSV standard)
TEXTURE_SUFFIXES = {
    'Base_Tex_SRGB': '_bsm',
    'NormalMap_Tex_NRM': '_nrm', 
    'SpecularMap_Tex_LIN': '_srm',
    'Translucent_Tex_LIN': '_trm',
    'Layer_Tex_SRGB': '_lym',
    'Detail_Tex_SRGB': '_dtm',
    'LightMap_Tex_SRGB': '_lbm',
    'AlphaMap_Tex_LIN': '_alp',
    'MetalnessMap_Tex_LIN': '_mtl',
}

# ============================================
# SECTION 2: DEBUG LOGGER
# ============================================

class DebugLogger:
    """Beautiful structured logging for FMDL import process"""
    
    def __init__(self):
        self.prefix = "=" * 50
        self.sub_prefix = "-" * 30
    
    # --- 2.1: Section Header ---
    def section(self, title):
        print(f"\n{self.prefix}")
        print(f"  {title}")
        print(f"{self.prefix}")
    
    # --- 2.2: Sub-Section Header ---
    def sub_section(self, title):
        print(f"\n{self.sub_prefix}")
        print(f"  {title}")
        print(f"{self.sub_prefix}")
    
    # --- 2.3: Operation Start ---
    def start(self, operation):
        print(f"\n[START] {operation}")
    
    # --- 2.4: Success Message ---
    def success(self, operation, details=""):
        if details:
            print(f"[SUCCESS] {operation} - {details}")
        else:
            print(f"[SUCCESS] {operation}")
    
    # --- 2.5: Error Message ---
    def error(self, operation, error_msg):
        print(f"[ERROR] {operation} - {error_msg}")
    
    # --- 2.6: Warning Message ---
    def warning(self, message):
        print(f"[WARNING] {message}")
    
    # --- 2.7: Info Message ---
    def info(self, message):
        print(f"[INFO] {message}")
    
    # --- 2.8: Result Summary ---
    def result(self, item, count):
        print(f"[RESULT] {item}: {count}")
    
    # --- 2.9: Debug Info ---
    def debug(self, message):
        print(f"[DEBUG] {message}")

logger = DebugLogger()

# ============================================
# SECTION 3: DICTIONARY MANAGER
# ============================================

class DictionaryManager:
    """Manages FMDL bone names and QAR texture path dictionaries"""
    
    def __init__(self, dict_folder):
        self.fmdl_dict = {}  # hash -> bone name
        self.qar_dict = {}   # hash -> texture path
        self.folder = Path(dict_folder)
        self.warning_count = 0
        self.max_warnings = 5
        
        logger.section("DICTIONARY MANAGER")
        logger.start("Initializing dictionaries")
        
        self.load_fmdl_dict()
        self.load_qar_dict()
        
        logger.success("Dictionary loading", 
                      f"FMDL: {len(self.fmdl_dict)}, QAR: {len(self.qar_dict)}")
    
    # --- 3.1: Load FMDL Bone Dictionary ---
    def load_fmdl_dict(self):
        logger.sub_section("Loading FMDL Dictionary")
        fmdl_path = self.folder / "fmdl_dictionary.txt"
        
        if not fmdl_path.exists():
            logger.error("FMDL dictionary", f"File not found: {fmdl_path}")
            return
        
        try:
            with open(fmdl_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                line_count = 0
                
                # Show first 5, ... , last 3 lines for debug
                logger.debug(f"First 5 lines:")
                for i, line in enumerate(lines[:5]):
                    logger.debug(f"  {i+1}: {line.strip()[:60]}")
                if len(lines) > 8:
                    logger.debug("  ...")
                    for i, line in enumerate(lines[-3:], len(lines)-2):
                        logger.debug(f"  {i}: {line.strip()[:60]}")
                
                for line_num, line in enumerate(lines, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    # Format 1: "name    -    hash"
                    parts = line.split('    -    ')
                    if len(parts) == 2:
                        name = parts[0].strip()
                        hash_str = parts[1].strip()
                    else:
                        # Format 2: name[spaces]hash
                        parts = line.rsplit(maxsplit=1)
                        if len(parts) == 2:
                            name, hash_str = parts
                            name = name.strip()
                            hash_str = hash_str.strip()
                        else:
                            self._log_limited_warning(f"Line {line_num}: Invalid format: {line[:50]}...")
                            continue
                    
                    try:
                        hash_val = int(hash_str, 16)
                        self.fmdl_dict[hash_val] = name
                        line_count += 1
                    except ValueError:
                        self._log_limited_warning(f"Line {line_num}: Invalid hash: {hash_str}")
                
                logger.success("FMDL dictionary", f"{line_count} entries loaded")
                if line_count > 0:
                    sample_name = list(self.fmdl_dict.values())[0]
                    sample_hash = next(h for h, n in self.fmdl_dict.items() if n == sample_name)
                    logger.debug(f"Sample: {sample_name} = {sample_hash:016X}")
                    
        except Exception as e:
            logger.error("FMDL dictionary", str(e))
    
    # --- 3.2: Load QAR Texture Dictionary ---
    def load_qar_dict(self):
        logger.sub_section("Loading QAR Dictionary")
        qar_path = self.folder / "qar_dictionary.txt"
        
        if not qar_path.exists():
            logger.warning("QAR dictionary", f"File not found: {qar_path} - will use hash-based texture lookup later")
            return
        
        try:
            with open(qar_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                line_count = 0
                
                # Show first 5, ... , last 3 lines for debug
                logger.debug(f"First 5 lines:")
                for i, line in enumerate(lines[:5]):
                    logger.debug(f"  {i+1}: {line.strip()[:60]}")
                if len(lines) > 8:
                    logger.debug("  ...")
                    for i, line in enumerate(lines[-3:], len(lines)-2):
                        logger.debug(f"  {i}: {line.strip()[:60]}")
                
                for line_num, line in enumerate(lines, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    # Format 1: "path    -    hash"
                    parts = line.split('    -    ')
                    if len(parts) == 2:
                        filepath = parts[0].strip()
                        hash_str = parts[1].strip()
                    else:
                        # Format 2: hash path or path[spaces]hash
                        parts = line.rsplit(maxsplit=1)
                        if len(parts) == 2:
                            first, second = parts
                            first = first.strip()
                            second = second.strip()
                            # Try both orders
                            try:
                                hash_val = int(first, 16)
                                filepath = second
                            except ValueError:
                                try:
                                    hash_val = int(second, 16)
                                    filepath = first
                                except ValueError:
                                    self._log_limited_warning(f"Line {line_num}: No valid hash found: {line[:50]}...")
                                    continue
                        else:
                            self._log_limited_warning(f"Line {line_num}: Invalid format: {line[:50]}...")
                            continue
                    
                    try:
                        hash_val = int(hash_str if 'hash_str' in locals() else first, 16)
                        self.qar_dict[hash_val] = filepath
                        line_count += 1
                    except ValueError:
                        self._log_limited_warning(f"Line {line_num}: Invalid hash: {hash_str}")
                
                logger.success("QAR dictionary", f"{line_count} entries loaded")
                if line_count > 0:
                    sample_path = list(self.qar_dict.values())[0]
                    sample_hash = next(h for h, p in self.qar_dict.items() if p == sample_path)
                    logger.debug(f"Sample: {sample_path[:50]}... = {sample_hash:016X}")
                    
        except Exception as e:
            logger.error("QAR dictionary", str(e))
    
    # --- 3.6: Limited Warning Logger ---
    def _log_limited_warning(self, message):
        """Limit warnings to 5 + 3 last ones"""
        if self.warning_count < self.max_warnings:
            logger.warning(message)
            self.warning_count += 1
        elif self.warning_count == self.max_warnings:
            logger.warning("... (more warnings suppressed)")
            self.warning_count += 1
    
    # --- 3.3: Get Bone Name by Hash ---
    def get_bone_name(self, hash_val):
        """Returns bone name from hash, fallback to hex format"""
        return self.fmdl_dict.get(hash_val, f"Bone_{hash_val:016X}")
    
    # --- 3.4: Get Texture Path by Hash ---
    def get_texture_path(self, hash_val):
        """Returns texture filepath from hash or None"""
        return self.qar_dict.get(hash_val, None)
    
    # --- 3.5: Reverse Lookup Hash by Name ---
    def lookup_name_hash(self, name):
        """Find hash by bone name (reverse lookup)"""
        for hash_val, bone_name in self.fmdl_dict.items():
            if bone_name == name:
                return hash_val
        return None










# ============================================
# SECTION 4: FMDL PARSER
# ============================================

class FMDLParser:
    """Universal FMDL Parser for MGSV:TPP, MGSV:GZ, PES"""
    
    # ✅ Class constants - داخل class
    MESH_BUFFER_FORMAT_ELEMENT_USAGE = {
        0: "POSITION",
        1: "NORMAL",
        2: "BINORMAL",
        3: "TANGENT",
        4: "TEXCOORD0",
        5: "TEXCOORD1",
        6: "TEXCOORD2",
        7: "TEXCOORD3",    
        8: "COLOR",
        9: "BLENDINDEX",
        10: "BLENDWEIGHT",
        11: "UNK_11",
    }
    
    MESH_BUFFER_FORMAT_ELEMENT_TYPE = {
        0: "BYTE",
        1: "UBYTE",
        2: "SHORT",
        3: "USHORT",   
        4: "FLOAT",
        5: "HALF",
        6: "R11G11B10",
        7: "UNK_7",
        8: "D3DCOLOR",
        9: "UNK_9",
        10: "INDEX16",
        11: "INDEX32",
    }
    
    ELEMENT_TYPE_SIZES = {
        0: 1,
        1: 1,
        2: 2,
        3: 2,   
        4: 4,
        5: 2,
        6: 12,
        7: 4,
        8: 4,
        9: 4,
        10: 2,
        11: 4
    }
    

   
    def __init__(self, filepath, dict_manager):
        self.filepath = Path(filepath)
        self.dict = dict_manager
        self.data = None
        
        # Storage for all parsed data (MGSV TPP/GZ + PES compatible)
        self.header = {}
        self.feature_headers = []
        self.buffer_headers = []
        self.bones = []
        self.materials = []
        self.meshes = []
        self.names = []
        self.paths = []
        self.texture_refs = []
        self.mesh_data_layouts = []
        self.mesh_buffer_headers = []
        self.mesh_buffer_format_elements = []
        self.file_mesh_buffer_headers = []
        self.ibuffer_slices = []
        self.aabbs = []
        
        logger.section("FMDL PARSER INITIALIZATION")
        logger.start(f"Reading: {self.filepath.name}")
        
        if not self.filepath.exists():
            raise FileNotFoundError(f"FMDL file not found: {filepath}")
        
        try:
            with open(self.filepath, 'rb') as f:
                self.data = f.read()
            size_mb = len(self.data)/1024/1024
            logger.success("File loaded", f"{len(self.data):,} bytes ({size_mb:.2f} MB)")
        except Exception as e:
            logger.error("File read", str(e))
            raise
    
    
    
    # 🔥 HELPER METHODS ← دقیقاً اینجا (بعد __init__, قبل public methods)
    def _read_matrix4x4(self, offset):
        """Read 4x4 float matrix (64 bytes)"""
        matrix = []
        for i in range(16):
            val = struct.unpack('<f', self.data[offset + i*4:offset + (i*4)+4])[0]
            matrix.append(val)
        return ma


    def _read_string(self, offset):
        """Read null-terminated string"""
        end = self.data.find(b'\x00', offset)  # ✅ درست شد!
        return self.data[offset:end].decode('utf-8', errors='ignore')


    # 🔥 همه Helper ها با TypeError فیکس
    def _get_feature_header(self, feature_id):
        """Get feature by ID (original method)"""
        for fh in self.feature_headers:
            if fh.get('id') == feature_id:
                return fh
        return None

    def _get_feature_header_by_name(self, name_pattern):
        """Universal feature finder - FIXED"""
        name_pattern = name_pattern.upper()
        for fh in self.feature_headers:
            fh_name = fh.get('name', b'').upper()
            if name_pattern in fh_name:
                return fh
        return None

    def _get_feature_header_by_count(self, expected_count):
        """Find feature by matching count"""
        for fh in self.feature_headers:
            if fh['total_count'] == expected_count:
                return fh
        return None


    def _get_format_for_vbuffer(self, vbuf_idx):
        """Dynamic format matching"""
        start_idx = vbuf_idx * 12 % len(self.mesh_buffer_format_elements)
        return self.mesh_buffer_format_elements[start_idx:start_idx+12]

    def _find_bone_name(self, offset, idx, count):
        """Universal bone name finder"""
        candidates = [offset + idx * 64, offset + idx * 32, offset + count * 8 + idx * 64]
        for pos in candidates:
            if pos + 64 < len(self.data):
                name = self._read_string(pos)
                if name and len(name.strip()) > 1:
                    return name
        return None

    def _parse_vbuffer_sample(self, vbuf, format_elements, stride, sample_count):
        """Parse sample vertices from buffer"""
        vertices = []
        for i in range(min(sample_count, vbuf['data_size'] // stride)):
            offset = vbuf['data_offset'] + i * stride
            vertex = self._read_single_vertex(offset, format_elements)
            vertices.append(vertex)
        return vertices

      
      
      

    
    # --- 4.1: Header Reading (TPP/GZ/PES Compatible) ---
    def read_header(self):
        """Parse FMDL main header - supports all Fox Engine versions"""
        logger.sub_section("FMDL Header (Multi-Version)")
        logger.start("Parsing header at offset 0x00")
        
        if len(self.data) < 0x38:
            raise ValueError(f"File too short ({len(self.data)} bytes) for FMDL header")
        
        # Verify magic
        magic = self.data[0:4]
        if magic != FMDL_MAGIC:
            raise ValueError(f"Invalid magic: {magic.hex()} (expected 'FMDL')")
        
        # Version as UINT32 (fixed: was float) - TPP=0x20150211, GZ=0x20140610
        version = struct.unpack('<I', self.data[0x04:0x08])[0]
        
        # Determine engine version for compatibility
        if version == VERSION_TPP:
            self.header['engine'] = 'TPP'
        elif version == VERSION_GZ:
            self.header['engine'] = 'GZ'
        elif version in [0x20140610, 0x20150211]:  # PES variants
            self.header['engine'] = 'PES'
        else:
            self.header['engine'] = 'UNKNOWN'
            logger.warning(f"Unknown version: 0x{version:08X}")
        
        self.header.update({
            'magic': magic.decode('ascii'),
            'version_raw': version,
            'version': f"0x{version:08X}",
            'file_desc_offset': struct.unpack('<I', self.data[0x08:0x0C])[0],
            'feature_flags': struct.unpack('<I', self.data[0x0C:0x10])[0],  # Added missing field
            'feature_types': struct.unpack('<I', self.data[0x10:0x14])[0],
            'buffer_types': struct.unpack('<I', self.data[0x18:0x1C])[0],
            'feature_count': struct.unpack('<I', self.data[0x20:0x24])[0],
            'buffer_count': struct.unpack('<I', self.data[0x24:0x28])[0],
            'features_data_offset': struct.unpack('<I', self.data[0x28:0x2C])[0],
            'features_data_size': struct.unpack('<I', self.data[0x2C:0x30])[0],
            'buffers_data_offset': struct.unpack('<I', self.data[0x30:0x34])[0],
            'buffers_data_size': struct.unpack('<I', self.data[0x34:0x38])[0],
        })
        
        # Version-specific logging
        logger.info(f"Engine: {self.header['engine']} (v{self.header['version']})")
        logger.info(f"Features: {self.header['feature_count']} | Buffers: {self.header['buffer_count']}")
        logger.info(f"Features data: 0x{self.header['features_data_offset']:08X}")
        logger.info(f"Buffers data: 0x{self.header['buffers_data_offset']:08X}")
        
        # Validate offsets
        if self.header['features_data_offset'] >= len(self.data):
            logger.warning(f"Features offset beyond EOF: 0x{self.header['features_data_offset']:X}")
        if self.header['buffers_data_offset'] >= len(self.data):
            logger.warning(f"Buffers offset beyond EOF: 0x{self.header['buffers_data_offset']:X}")
            
        logger.success("Header parsed", f"{self.header['engine']} compatible")


    # --- 4.2: Feature Headers (TPP/GZ/PES Compatible) ---
    def read_feature_headers(self):
        """Parse ALL Fox Engine feature headers with bounds checking"""
        logger.sub_section("Feature Headers")
        logger.start(f"Reading {self.header['feature_count']} features")
        
        offset = self.header['file_desc_offset']
        expected_size = self.header['feature_count'] * 8
        
        if offset + expected_size > len(self.data):
            raise ValueError(f"Feature headers beyond EOF: 0x{offset:X}+{expected_size}")
        
        self.feature_headers.clear()
        
        for i in range(self.header['feature_count']):
            fh_offset = offset + (i * 8)
            
            feature_type = self.data[fh_offset]              # 1 byte
            count_overflow = self.data[fh_offset + 1]        # 1 byte  
            entry_count = struct.unpack('<H', self.data[fh_offset+2:fh_offset+4])[0]  # 2 bytes
            data_offset = struct.unpack('<I', self.data[fh_offset+4:fh_offset+8])[0]  # 4 bytes
            
            total_count = (count_overflow * 0x10000) + entry_count
            
            # Validate data_offset
            data_abs_offset = self.header['features_data_offset'] + data_offset
            if data_abs_offset >= len(self.data):
                logger.warning(f"Feature {i}: Invalid data_offset 0x{data_offset:X}")
                data_offset = 0
            
            self.feature_headers.append({
                'index': i,
                'type': feature_type,
                'type_name': self.get_feature_type_name(feature_type),
                'count_overflow': count_overflow,
                'entry_count': entry_count,
                'total_count': total_count,
                'data_offset': data_offset,
                'abs_data_offset': data_abs_offset,
                'valid': data_offset != 0
            })
            
            # Log only critical features (less spam)
            if feature_type in [0,3,4,6,9,10,11,13,14,17,21,22]:
                logger.info(f"F{feature_type:2d}: {self.get_feature_type_name(feature_type):<20} "
                           f"[{total_count:>6}] @ 0x{data_offset:08X}")
        
        # Summary of critical features
        critical = {fh['type']: fh['total_count'] for fh in self.feature_headers 
                    if fh['type'] in [0,3,4,6]}
        logger.success("Features parsed", f"{len(self.feature_headers)} total, critical: {critical}")
        
        return len(self.feature_headers)

    # --- 4.2.1: Complete Feature Type Names (from fmdl.bt + FMDL-Studio-v2) ---
    def get_feature_type_name(self, type_id):
        """Complete feature type mapping for TPP/GZ/PES"""
        types = {
            # Core MGSV/PES features
            0: "BONE_DEFS",
            1: "MESH_DEFS_GROUP_HEADERS", 
            2: "MESH_DEFS_GROUP_DEFS",
            3: "MESH_DEFS",
            4: "MATERIAL_INSTANCES",
            5: "BONE_GROUPS",
            6: "TEXTURE_REFS",
            7: "MATERIAL_PARAMS",
            8: "SHADER_ALIASES",
            9: "MESH_DATA_LAYOUTS",
            10: "MESH_BUFFER_HEADERS",
            11: "FORMAT_ELEMENTS",
            12: "STRING_HEADER",
            13: "AABBS",
            14: "FILE_MESH_BUFFERS",
            
            # LOD & Indexing
            16: "LOD_INFO",
            17: "IBUFFER_SLICES",
            
            # Hash tables
            21: "PATH_HASHES",
            22: "NAME_HASHES",
            
            # Unknown but present in some files
            18: "UNK_VISIBILITY",
            19: "UNK_19", 
            20: "UNK_20",
            23: "UNK_23",  # PES-specific
        }
        return types.get(type_id, f"UNK_{type_id:02X}")

    # --- 4.3: Buffer Headers (Vertex/Index/Material Data) ---
    def read_buffer_headers(self):
        """Parse raw buffer data locations (VERTICES, INDICES, MATERIALS)"""
        logger.sub_section("Buffer Headers")
        offset = self.header['file_desc_offset'] + (self.header['feature_count'] * 8)
        expected_size = self.header['buffer_count'] * 12
        
        if offset + expected_size > len(self.data):
            logger.warning(f"Buffer headers truncated: need {expected_size}, got {len(self.data)-offset}")
            return 0
        
        logger.start(f"Reading {self.header['buffer_count']} buffers")
        self.buffer_headers.clear()
        
        for i in range(self.header['buffer_count']):
            bh_offset = offset + (i * 12)
            
            buffer_type = struct.unpack('<I', self.data[bh_offset:bh_offset+4])[0]
            data_offset = struct.unpack('<I', self.data[bh_offset+4:bh_offset+8])[0]
            data_size = struct.unpack('<I', self.data[bh_offset+8:bh_offset+12])[0]
            
            # Absolute offset validation
            abs_offset = self.header['buffers_data_offset'] + data_offset
            valid = (data_size > 0 and abs_offset + data_size <= len(self.data))
            
            self.buffer_headers.append({
                'index': i,
                'type': buffer_type,
                'type_name': self.get_buffer_type_name(buffer_type),
                'data_offset': data_offset,
                'abs_offset': abs_offset,
                'data_size': data_size,
                'valid': valid
            })
            
            if valid or i < 3:  # Log first 3 + valid ones
                logger.info(f"B{i}: {self.get_buffer_type_name(buffer_type):<12} "
                           f"[{data_size:,} bytes] @ 0x{data_offset:08X}")
        
        # Buffer summary
        vbuffer_count = sum(1 for b in self.buffer_headers if b['type'] == 2)
        logger.success("Buffers parsed", f"{len(self.buffer_headers)} total, {vbuffer_count} VBuffers")
        return len(self.buffer_headers)

    # --- 4.3.1: Complete Buffer Type Names ---
    def get_buffer_type_name(self, type_id):
        """Buffer types from FMDL-Studio-v2/FoxMesh.cs"""
        types = {
            0: "MATERIAL_PARAMS",
            1: "INDEX_BUFFER",      # Added!
            2: "VERTEX_BUFFER",     # Fixed name
            3: "STRINGS",  
            4: "UNK_4",             # PES-specific
        }
        return types.get(type_id, f"UNK_{type_id}")


        
        
        
        
        
        
        
        
        
        
        
               
    # --- 4.4: Names & Paths (StrCode64/PathCode64 - TPP/GZ/PES) ---
    def read_names(self):
        """Parse NAME_HASHES (feature 22) - bone/material/texture names"""
        logger.sub_section("Names (StrCode64)")
        fh = self._get_feature_header(22)  # NAME_HASHES
        
        if not fh:
            logger.warning("No NAME_HASHES feature (22)")
            return 0
        
        offset = self.header['features_data_offset'] + fh['data_offset']
        count = fh['total_count']
        
        # Bounds check
        if offset + count * 8 > len(self.data):
            logger.warning(f"Names truncated: need {count*8} bytes from 0x{offset:X}")
            count = (len(self.data) - offset) // 8
        
        logger.start(f"Loading {count} names @ 0x{offset:08X}")
        self.names.clear()
        
        for i in range(count):
            name_offset = offset + (i * 8)
            if name_offset + 8 > len(self.data):
                break
                
            name_hash = struct.unpack('<Q', self.data[name_offset:name_offset+8])[0]
            
            # Dictionary lookup + fallback (PES/MGSV compatible)
            resolved_name = self.dict.get_bone_name(name_hash) if self.dict else None
            display_name = resolved_name or f"N{i:04d}_{name_hash:016X}"
            
            self.names.append({
                'index': i,
                'hash': name_hash,
                'resolved_name': resolved_name,
                'display_name': display_name,
                'hash_hex': f"{name_hash:016X}"
            })
        
        logger.success("Names loaded", f"{len(self.names)} entries")
        
        # Smart sample logging (first 3 + bone-related)
        bone_names = [n for n in self.names[:10] if "bone" in n['display_name'].lower() or n['resolved_name']]
        if self.names:
            logger.debug(f"First: {self.names[0]['display_name']}")
            logger.debug(f"Last:  {self.names[-1]['display_name']}")
            if bone_names:
                logger.debug(f"Bone sample: {bone_names[0]['display_name']}")
        
        return len(self.names)

    # --- 4.4.1: Paths (PathCode64) - Texture/Material paths ---
    def read_paths(self):
        """Parse PATH_HASHES (feature 21) - texture file paths"""
        logger.sub_section("Paths (PathCode64)")
        fh = self._get_feature_header(21)  # PATH_HASHES
        
        if not fh:
            logger.warning("No PATH_HASHES feature (21)")
            return 0
        
        offset = self.header['features_data_offset'] + fh['data_offset']
        count = fh['total_count']
        
        # Bounds check
        if offset + count * 8 > len(self.data):
            logger.warning(f"Paths truncated: need {count*8} bytes")
            count = (len(self.data) - offset) // 8
        
        logger.start(f"Loading {count} paths @ 0x{offset:08X}")
        self.paths.clear()
        
        for i in range(count):
            path_offset = offset + (i * 8)
            if path_offset + 8 > len(self.data):
                break
                
            path_hash = struct.unpack('<Q', self.data[path_offset:path_offset+8])[0]
            
            # QAR dictionary lookup (texture paths)
            resolved_path = self.dict.get_texture_path(path_hash) if self.dict else None
            
            # Fallback: construct from hash + suffix patterns
            if not resolved_path:
                # Common Fox Engine texture naming
                suffix = TEXTURE_SUFFIXES.get(self.header['engine'], '_tex')
                resolved_path = f"tex_{path_hash:016X}{suffix}"
            
            self.paths.append({
                'index': i,
                'hash': path_hash,
                'resolved_path': resolved_path,
                'hash_hex': f"{path_hash:016X}",
                'is_texture': 'tex_' in resolved_path.lower() or '.ftex' in resolved_path.lower()
            })
        
        logger.success("Paths loaded", f"{len(self.paths)} entries")
        
        # Texture path samples
        texture_paths = [p for p in self.paths[:5] if p['is_texture']]
        if self.paths:
            logger.debug(f"First: {self.paths[0]['resolved_path'][:60]}")
            if texture_paths:
                logger.debug(f"Texture: {texture_paths[0]['resolved_path'][:60]}")
        
        return len(self.paths)

    # --- 4.4.2: Feature Header Lookup (Optimized) ---
    def _get_feature_header(self, feature_type):
        """Fast lookup for feature header by type"""
        if not self.feature_headers:
            logger.warning("_get_feature_header called before read_feature_headers")
            return None
        
        for fh in self.feature_headers:
            if fh['type'] == feature_type:
                # Validate feature data exists
                abs_offset = self.header['features_data_offset'] + fh['data_offset']
                if abs_offset + fh['total_count'] * 8 <= len(self.data):
                    return fh
                else:
                    logger.warning(f"Feature {feature_type} data truncated")
        
        logger.debug(f"No valid feature header found for type {feature_type}")
        return None

      
  
  
  
  
  
  
  
  
  
  
  
    # --- 4.5: Bone Definitions (اصلی - بدون Y-up fix) ---
    def read_bone_defs(self):
        """کد اصلی - بدون هیچ coordinate fix"""
        logger.sub_section("Reading Bone Definitions")
        fh = self._get_feature_header(0)  # BONE_DEFS
        
        if not fh:
            logger.warning("No BONE_DEFS feature found")
            return
        
        offset = self.header['features_data_offset'] + fh['data_offset']
        count = fh['total_count']
        
        logger.start(f"Reading {count} bones at 0x{offset:X}")
        
        for i in range(count):
            bone_offset = offset + (i * 0x30)  # 48 bytes
            
            name_index = struct.unpack('<H', self.data[bone_offset:bone_offset+2])[0]
            parent_index = struct.unpack('<h', self.data[bone_offset+2:bone_offset+4])[0]
            aabb_index = struct.unpack('<H', self.data[bone_offset+4:bone_offset+6])[0]
            flags = struct.unpack('<H', self.data[bone_offset+6:bone_offset+8])[0]
            
            # Skip 8 bytes padding @ 0x08-0x0F
            
            # LocalPosition @ 0x10 (Vector4) - RAW FMDL values
            local_x = struct.unpack('<f', self.data[bone_offset+0x10:bone_offset+0x14])[0]
            local_y = struct.unpack('<f', self.data[bone_offset+0x14:bone_offset+0x18])[0]  # ✅ Raw Fox Y-up
            local_z = struct.unpack('<f', self.data[bone_offset+0x18:bone_offset+0x1C])[0]
            local_w = struct.unpack('<f', self.data[bone_offset+0x1C:bone_offset+0x20])[0]
            
            # WorldPosition @ 0x20 (Vector4) - RAW FMDL values
            world_x = struct.unpack('<f', self.data[bone_offset+0x20:bone_offset+0x24])[0]
            world_y = struct.unpack('<f', self.data[bone_offset+0x24:bone_offset+0x28])[0]  # ✅ Raw Fox Y-up
            world_z = struct.unpack('<f', self.data[bone_offset+0x28:bone_offset+0x2C])[0]
            world_w = struct.unpack('<f', self.data[bone_offset+0x2C:bone_offset+0x30])[0]
            
            # Original naming - دقیقاً مثل قبل
            name = "Unknown"
            if name_index < len(self.names):
                name = self.names[name_index].get('name', f"Bone_{name_index}")
            
            self.bones.append({
                'index': i,
                'name': name,
                'name_index': name_index,
                'parent': parent_index,
                'aabb_index': aabb_index,
                'flags': flags,
                'local_position': (local_x, local_y, local_z),  # ✅ Raw FMDL - سر و ته
                'world_position': (world_x, world_y, world_z),  # ✅ Raw FMDL - سر و ته
            })
        
        logger.success("Bones read", f"{len(self.bones)} bones")
        if self.bones:
            logger.debug(f"First bone: {self.bones[0]['name']} (parent: {self.bones[0]['parent']})")
            logger.debug(f"Root bone count: {sum(1 for b in self.bones if b['parent'] == -1)}")
            logger.info("Raw FMDL coordinates - 180°X rotation at final assembly")

    
    
    
    
    
    
    
    
    
    
    # --- 4.6: Mesh Definitions (TPP/GZ/PES Compatible - Raw FMDL) ---
    def read_mesh_defs(self):
        """Parse MESH_DEFS (feature 3) - Raw Fox Engine mesh data"""
        logger.sub_section("Reading Mesh Definitions")
        fh = self._get_feature_header(3)  # MESH_DEFS
        
        if not fh:
            logger.warning("No MESH_DEFS feature found")
            return
        
        offset = self.header['features_data_offset'] + fh['data_offset']
        count = fh['total_count']
        mesh_size = 0x30  # 48 bytes
        
        # Bounds check
        if offset + count * mesh_size > len(self.data):
            logger.warning(f"Mesh defs truncated: {count} need {count*mesh_size} bytes")
            count = (len(self.data) - offset) // mesh_size
        
        logger.start(f"Reading {count} meshes @ 0x{offset:08X}")
        self.meshes.clear()
        
        for i in range(count):
            mesh_offset = offset + (i * mesh_size)
            if mesh_offset + mesh_size > len(self.data):
                break
            
            # Flags @ 0x00 (4 bytes)
            flags = struct.unpack('<I', self.data[mesh_offset:mesh_offset+4])[0]
            
            # MaterialInstanceIndex @ 0x04 (2 bytes) - 1-based → 0-based
            material_index_raw = struct.unpack('<H', self.data[mesh_offset+4:mesh_offset+6])[0]
            material_index = material_index_raw - 1 if material_index_raw > 0 else -1
            
            # BoneGroupIndex @ 0x06 (2 bytes)
            bone_group = struct.unpack('<H', self.data[mesh_offset+6:mesh_offset+8])[0]
            
            # DataLayoutIndex @ 0x08 (2 bytes)
            data_layout = struct.unpack('<H', self.data[mesh_offset+8:mesh_offset+10])[0]
            
            # VertexCount @ 0x0A (2 bytes)
            vertex_count = struct.unpack('<H', self.data[mesh_offset+10:mesh_offset+12])[0]
            
            # VerticesStartIndex @ 0x0C (2 bytes) - VBuffer offset
            vert_start = struct.unpack('<H', self.data[mesh_offset+12:mesh_offset+14])[0]
            
            # Padding @ 0x0E (2 bytes)
            
            # HighLOD Slice @ 0x10-0x18 (Index buffer slice)
            lod_flags = struct.unpack('<I', self.data[mesh_offset+12:mesh_offset+16])[0]  # Fixed offset
            start_index = struct.unpack('<I', self.data[mesh_offset+16:mesh_offset+20])[0]
            index_count = struct.unpack('<I', self.data[mesh_offset+20:mesh_offset+24])[0]
            
            # IBufferSlicesStartIndex @ 0x18 (4 bytes)
            ibuffer_start = struct.unpack('<I', self.data[mesh_offset+24:mesh_offset+28])[0]
            
            # Skip 0x1C-0x30 padding/reserved
            
            self.meshes.append({
                'index': i,
                'flags': flags,
                'flags_hex': f"0x{flags:08X}",
                'material_index': material_index,
                'material_index_raw': material_index_raw,
                'bone_group': bone_group,
                'data_layout_index': data_layout,
                'vertex_count': vertex_count,
                'vertices_start_index': vert_start,  # VBuffer offset
                'lod_flags': lod_flags,
                'start_index': start_index,          # Index buffer start
                'index_count': index_count,          # Triangle count * 3
                'ibuffer_slices_start': ibuffer_start,
                'mesh_name': f"Mesh_{i:03d}",        # Default name
            })
            
            # Reduced logging (only first 5 + summary)
            if i < 5:
                logger.info(f"M{i:2d}: mat={material_index_raw}/{material_index}, "
                           f"V={vertex_count}, I={index_count}, layout={data_layout}")
        
        logger.success("Meshes parsed", f"{len(self.meshes)} meshes")
        
        # Mesh statistics
        total_verts = sum(m['vertex_count'] for m in self.meshes)
        total_indices = sum(m['index_count'] for m in self.meshes)
        skinned_meshes = sum(1 for m in self.meshes if m['bone_group'] > 0)
        
        logger.result("Total vertices", f"{total_verts:,}")
        logger.result("Total indices", f"{total_indices:,}")
        logger.info(f"Skinned meshes: {skinned_meshes}/{len(self.meshes)}")
        
        return len(self.meshes)











    # --- 4.7: Material Instance Headers (TPP/GZ/PES Compatible) ---
    def read_materials(self):
        """Parse MATERIAL_INSTANCES (feature 4) - Complete material pipeline"""
        logger.sub_section("Reading Material Instance Headers")
        fh = self._get_feature_header(4)  # MATERIAL_INSTANCE_HEADERS
        
        if not fh:
            logger.warning("No MATERIAL_INSTANCE_HEADERS feature found")
            return 0
        
        offset = self.header['features_data_offset'] + fh['data_offset']
        count = fh['total_count']
        mat_size = 0x20  # 32 bytes
        
        # Bounds check
        if offset + count * mat_size > len(self.data):
            logger.warning(f"Materials truncated: {count} need {count*mat_size} bytes")
            count = (len(self.data) - offset) // mat_size
        
        logger.start(f"Reading {count} materials @ 0x{offset:08X}")
        self.materials.clear()
        
        for i in range(count):
            mat_offset = offset + (i * mat_size)
            if mat_offset + mat_size > len(self.data):
                break
            
            # Material name index @ 0x00 (2 bytes) - StrCode32
            name_index = struct.unpack('<H', self.data[mat_offset:mat_offset+2])[0]
            
            # Padding @ 0x02 (2 bytes)
            
            # Display name index @ 0x04 (2 bytes) - Material display name
            material_name_index = struct.unpack('<H', self.data[mat_offset+4:mat_offset+6])[0]
            
            # Counts @ 0x06-0x07
            texture_count = self.data[mat_offset+6]              # 1 byte
            vector_count = self.data[mat_offset+7]               # 1 byte
            
            # Parameter table indices @ 0x08-0x0C
            texture_start = struct.unpack('<H', self.data[mat_offset+8:mat_offset+10])[0]
            vector_start = struct.unpack('<H', self.data[mat_offset+10:mat_offset+12])[0]
            
            # Padding @ 0x0C-0x20 (20 bytes reserved)
            
            # Resolve material names (priority pipeline)
            mat_name = f"Mat_{i:03d}"
            if name_index < len(self.names):
                mat_name = self.names[name_index].get('name', f"Mat_{name_index}")
            elif self.dict and name_index > 0:
                mat_name = self.dict.get_bone_name(name_index) or f"Mat_{i:03d}"
            
            display_name = f"Display_{material_name_index}"
            if material_name_index < len(self.names):
                display_name = self.names[material_name_index].get('name', display_name)
            
            # Texture references (safe bounds)
            texture_refs = []
            if hasattr(self, 'texture_refs') and self.texture_refs:
                for t in range(texture_count):
                    ref_idx = texture_start + t
                    if 0 <= ref_idx < len(self.texture_refs):
                        texture_refs.append(self.texture_refs[ref_idx])
            
            # Material metadata
            self.materials.append({
                'index': i,
                'name': mat_name,
                'name_index': name_index,
                'display_name': display_name,
                'material_name_index': material_name_index,
                'texture_count': texture_count,
                'vector_count': vector_count,
                'texture_start': texture_start,
                'vector_start': vector_start,
                'texture_refs': texture_refs,
                'flags': 0,  # Placeholder for shader flags
                'shader_name': None,  # Resolved later
            })
            
            # Log only complex materials
            if texture_count > 0 or vector_count > 0 or i < 3:
                logger.info(f"M{i:2d}: {mat_name:<20} T={texture_count} V={vector_count}")
        
        logger.success("Materials parsed", f"{len(self.materials)} materials")
        
        # Material statistics
        textured_mats = sum(1 for m in self.materials if m['texture_count'] > 0)
        complex_mats = sum(1 for m in self.materials if m['texture_count'] + m['vector_count'] > 2)
        
        logger.info(f"Textured: {textured_mats}/{len(self.materials)}")
        logger.info(f"Complex: {complex_mats}/{len(self.materials)}")
        
        return len(self.materials)

        
        
        
        
        

    
    
    # --- 4.8: Texture References (TPP/GZ/PES Compatible) ---
    def read_texture_refs(self):
        """Parse TEXTURE_REFS (feature 6) - Complete texture lookup pipeline"""
        logger.sub_section("Reading Texture References")
        fh = self._get_feature_header(6)  # TEXTURE_REFS
        
        if not fh:
            logger.warning("No TEXTURE_REFS feature (6)")
            return 0
        
        offset = self.header['features_data_offset'] + fh['data_offset']
        count = fh['total_count']
        texref_size = 8  # 8 bytes per reference
        
        # Bounds check
        if offset + count * texref_size > len(self.data):
            logger.warning(f"Texture refs truncated: {count} need {count*texref_size} bytes")
            count = (len(self.data) - offset) // texref_size
        
        logger.start(f"Reading {count} texture refs @ 0x{offset:08X}")
        self.texture_refs.clear()
        
        for i in range(count):
            tex_offset = offset + (i * texref_size)
            if tex_offset + texref_size > len(self.data):
                break
            
            # Texture name index @ 0x00 (2 bytes) - StrCode32
            name_index = struct.unpack('<H', self.data[tex_offset:tex_offset+2])[0]
            
            # Texture path index @ 0x02 (2 bytes) - PathCode32 index
            path_index = struct.unpack('<H', self.data[tex_offset+2:tex_offset+4])[0]
            
            # Padding/reserved @ 0x04-0x08 (4 bytes)
            
            # Name resolution (priority pipeline)
            tex_name = f"Tex_{name_index:04X}"
            if name_index < len(self.names):
                tex_name = self.names[name_index].get('name', tex_name) or \
                          self.names[name_index].get('resolved_name', tex_name) or \
                          self.names[name_index].get('display_name', tex_name)
            
            # Path resolution (priority pipeline)
            tex_path = f"Path_{path_index:04X}"
            if path_index < len(self.paths):
                tex_path = self.paths[path_index].get('path', tex_path) or \
                          self.paths[path_index].get('resolved_path', tex_path)
            elif self.dict:
                # Fallback: try dictionary lookup by name
                tex_path = self.dict.get_texture_path_by_name(tex_name) or tex_path
            
            # Texture type detection
            tex_type = "unknown"
            tex_path_lower = tex_path.lower()
            if any(ext in tex_path_lower for ext in ['.dds', '.ftex', '_tex']):
                tex_type = "diffuse"
            elif any(ext in tex_path_lower for ext in ['_nrm', '_nor', 'normal']):
                tex_type = "normal"
            elif any(ext in tex_path_lower for ext in ['_sp', '_spec', 'spec']):
                tex_type = "specular"
            
            self.texture_refs.append({
                'index': i,
                'name_index': name_index,
                'name': tex_name,
                'path_index': path_index,
                'path': tex_path,
                'type': tex_type,
                'hash': self.names[name_index].get('hash', 0) if name_index < len(self.names) else 0,
            })
        
        logger.success("Texture refs parsed", f"{len(self.texture_refs)} refs")
        
        # Texture statistics
        diffuse_count = sum(1 for t in self.texture_refs if t['type'] == 'diffuse')
        normal_count = sum(1 for t in self.texture_refs if t['type'] == 'normal')
        unique_paths = len(set(t['path'] for t in self.texture_refs))
        
        logger.info(f"Diffuse: {diffuse_count}, Normal: {normal_count}")
        logger.info(f"Unique textures: {unique_paths}/{len(self.texture_refs)}")
        
        # Sample logging
        if self.texture_refs:
            logger.debug(f"Sample: {self.texture_refs[0]['name']} -> {self.texture_refs[0]['path'][:60]}")
        
        return len(self.texture_refs)

    
    
    
    
    
    
    
    
    
    
    
    
    # --- 4.9: Mesh Data Layout Descriptions (Critical for Vertex Format) ---
    def read_mesh_data_layouts(self):
        """Parse MESH_DATA_LAYOUTS (feature 9) - Vertex format definitions"""
        logger.sub_section("Reading Mesh Data Layout Descriptions")
        fh = self._get_feature_header(9)  # MESH_DATA_LAYOUT_DESCS
        
        if not fh:
            logger.warning("No MESH_DATA_LAYOUT_DESCS feature (9)")
            return 0
        
        offset = self.header['features_data_offset'] + fh['data_offset']
        count = fh['total_count']
        layout_size = 8  # 8 bytes per layout
        
        # Bounds check
        if offset + count * layout_size > len(self.data):
            logger.warning(f"Layouts truncated: {count} need {count*layout_size} bytes")
            count = (len(self.data) - offset) // layout_size
        
        logger.start(f"Reading {count} layouts @ 0x{offset:08X}")
        self.mesh_data_layouts.clear()
        
        for i in range(count):
            layout_offset = offset + (i * layout_size)
            if layout_offset + layout_size > len(self.data):
                break
            
            # Layout header (packed 8 bytes)
            buffer_count = self.data[layout_offset]                    # 1 byte
            format_element_count = self.data[layout_offset + 1]        # 1 byte
            unknown0 = self.data[layout_offset + 2]                    # 1 byte (vertex stride?)
            uv_count = self.data[layout_offset + 3]                    # 1 byte
            
            buffer_headers_start = struct.unpack('<H', self.data[layout_offset+4:layout_offset+6])[0]  # 2 bytes
            format_elements_start = struct.unpack('<H', self.data[layout_offset+6:layout_offset+8])[0] # 2 bytes
            
            # Calculate expected stride (critical for vertex reading)
            expected_stride = format_element_count * 16  # Average 16 bytes per attribute
            if buffer_count > 1:
                expected_stride *= buffer_count
            
            # Validate references
            buffer_valid = buffer_headers_start < len(self.mesh_buffer_headers) if hasattr(self, 'mesh_buffer_headers') else True
            format_valid = format_elements_start < len(self.mesh_buffer_format_elements) if hasattr(self, 'mesh_buffer_format_elements') else True
            
            self.mesh_data_layouts.append({
                'index': i,
                'buffer_count': buffer_count,
                'format_element_count': format_element_count,
                'unknown0': unknown0,
                'uv_count': uv_count,
                'buffer_headers_start': buffer_headers_start,
                'format_elements_start': format_elements_start,
                'expected_stride': expected_stride,
                'buffer_valid': buffer_valid,
                'format_valid': format_valid,
                'layout_name': f"Layout_{i:02d}_{buffer_count}b_{format_element_count}e_{uv_count}uv",
            })
            
            # Log all layouts (critical for debugging vertex issues)
            logger.info(f"L{i:2d}: {buffer_count}b/{format_element_count}e/{uv_count}uv "
                       f"stride~{expected_stride} bh={buffer_headers_start} fe={format_elements_start}")
        
        logger.success("Layouts parsed", f"{len(self.mesh_data_layouts)} layouts")
        
        # Layout statistics (predicts vertex complexity)
        multi_buffer = sum(1 for l in self.mesh_data_layouts if l['buffer_count'] > 1)
        high_poly = sum(1 for l in self.mesh_data_layouts if l['format_element_count'] > 12)
        
        logger.info(f"Multi-buffer: {multi_buffer}/{len(self.mesh_data_layouts)}")
        logger.info(f"High-complexity: {high_poly}/{len(self.mesh_data_layouts)}")
        
        return len(self.mesh_data_layouts)












    # --- 4.10: Mesh Buffer Headers (Vertex Stream Headers - Critical!) ---
    def read_mesh_buffer_headers(self):
        """Parse MESH_BUFFER_HEADERS (feature 10) - Vertex buffer stream definitions"""
        logger.sub_section("Reading Mesh Buffer Headers")
        fh = self._get_feature_header(10)  # MESH_BUFFER_HEADERS
        
        if not fh:
            logger.warning("No MESH_BUFFER_HEADERS feature (10)")
            return 0
        
        offset = self.header['features_data_offset'] + fh['data_offset']
        count = fh['total_count']
        header_size = 0x10  # 16 bytes
        
        # Bounds check
        if offset + count * header_size > len(self.data):
            logger.warning(f"Buffer headers truncated: {count} need {count*header_size} bytes")
            count = (len(self.data) - offset) // header_size
        
        logger.start(f"Reading {count} buffer headers @ 0x{offset:08X}")
        self.mesh_buffer_headers.clear()
        
        for i in range(count):
            buf_offset = offset + (i * header_size)
            if buf_offset + header_size > len(self.data):
                break
            
            # Packed header (first 4 bytes)
            file_buffer_index = self.data[buf_offset]              # 1 byte - VBuffer index
            format_element_count = self.data[buf_offset + 1]       # 1 byte - attribute count
            stride = self.data[buf_offset + 2]                     # 1 byte - **VERTEX STRIDE (bytes)!**
            bind_slot = self.data[buf_offset + 3]                  # 1 byte - shader binding slot
            
            # Data offset @ 0x04 (4 bytes) - offset in VBuffer
            data_offset = struct.unpack('<I', self.data[buf_offset+4:buf_offset+8])[0]
            
            # Padding/reserved @ 0x08-0x10 (8 bytes)
            
            # Cross-reference validation
            layout_match = None
            if i < len(self.mesh_data_layouts):
                layout_match = self.mesh_data_layouts[i]
                stride_match = abs(stride - layout_match.get('expected_stride', stride)) < 16
            
            # Vertex buffer info (cross-reference)
            vbuffer_info = None
            if hasattr(self, 'buffer_headers') and file_buffer_index < len(self.buffer_headers):
                vbuf = self.buffer_headers[file_buffer_index]
                if vbuf['type'] == 2:  # VERTEX_BUFFER
                    vbuffer_info = f"VBuf{file_buffer_index}@{vbuf['data_size']:,}B"
            
            self.mesh_buffer_headers.append({
                'index': i,
                'file_buffer_index': file_buffer_index,
                'vbuffer_info': vbuffer_info,
                'format_element_count': format_element_count,
                'stride': stride,  # 🔥 VERTEX STRIDE - حیاتی!
                'stride_hex': f"0x{stride:02X}",
                'bind_slot': bind_slot,
                'data_offset': data_offset,
                'layout_match': layout_match['index'] if layout_match else -1,
                'stride_valid': stride > 0 and stride <= 128,  # Typical range
                'header_name': f"VStream_{i}_{stride}B_{format_element_count}attr",
            })
            
            # Log ALL headers (critical for vertex debugging)
            status = "✓" if self.mesh_buffer_headers[-1]['stride_valid'] else "✗"
            logger.info(f"[{status}] H{i:2d}: {stride}B/{format_element_count}attr "
                       f"slot={bind_slot} vbuf={file_buffer_index} "
                       f"off=0x{data_offset:06X} {'MATCH' if stride_match else 'MISMATCH'}")
        
        logger.success("Buffer headers parsed", f"{len(self.mesh_buffer_headers)} headers")
        
        # Critical statistics
        invalid_stride = sum(1 for h in self.mesh_buffer_headers if not h['stride_valid'])
        multi_stream = sum(1 for h in self.mesh_buffer_headers if h['bind_slot'] > 0)
        
        logger.warning(f"Invalid strides: {invalid_stride}/{len(self.mesh_buffer_headers)}")
        logger.info(f"Multi-stream: {multi_stream}/{len(self.mesh_buffer_headers)}")
        
        return len(self.mesh_buffer_headers)

        
    
    
    
    
    
    
    
    
    
    
    
    
    # --- 4.11: Mesh Buffer Format Elements (FIXED) ---
    def read_mesh_buffer_format_elements(self):
        """Parse MESH_BUFFER_FORMAT_ELEMENTS (feature 11) - Vertex attribute layout"""
        logger.sub_section("Reading Mesh Buffer Format Elements")
        fh = self._get_feature_header(11)
        
        if not fh:
            logger.warning("No MESH_BUFFER_FORMAT_ELEMENTS feature (11)")
            return 0
        
        offset = self.header['features_data_offset'] + fh['data_offset']
        count = fh['total_count']
        elem_size = 4
        
        if offset + count * elem_size > len(self.data):
            count = (len(self.data) - offset) // elem_size
        
        logger.start(f"Reading {count} format elements @ 0x{offset:08X}")
        self.mesh_buffer_format_elements.clear()
        
        for i in range(count):
            elem_offset = offset + (i * elem_size)
            if elem_offset + elem_size > len(self.data):
                break
            
            usage = self.data[elem_offset]
            elem_type = self.data[elem_offset + 1]
            elem_offset_val = struct.unpack('<H', self.data[elem_offset+2:elem_offset+4])[0]
            
            usage_name = self.MESH_BUFFER_FORMAT_ELEMENT_USAGE.get(usage, f"UNK_{usage:02X}")
            type_name = self.MESH_BUFFER_FORMAT_ELEMENT_TYPE.get(elem_type, f"UNK_{elem_type:02X}")
            byte_size = self.ELEMENT_TYPE_SIZES.get(elem_type, 4)
            
            # ✅ FIX: Real stride from mesh_buffer_headers
            stride_valid = True
            stride = 0
            if i < len(self.mesh_buffer_headers) and self.mesh_buffer_headers[i].get('stride'):
                stride = self.mesh_buffer_headers[i]['stride']
                if elem_offset_val + byte_size > stride:
                    stride_valid = False
            
            # Default stride if not available
            if stride == 0:
                stride = 512  # Fox Engine standard
                stride_valid = True
            
            elem = {
                'index': i, 'usage': usage, 'usage_name': usage_name,
                'type': elem_type, 'type_name': type_name,
                'offset': elem_offset_val, 'byte_size': byte_size,
                'stride': stride, 'stride_valid': stride_valid
            }
            self.mesh_buffer_format_elements.append(elem)
            
            if i < 20 or not stride_valid:
                status = "✓" if stride_valid else "✗"
                logger.info(f"[{status}] E{i:3d}: {usage_name:<12} {type_name:<8} "
                           f"@0x{elem_offset_val:04X} ({byte_size}B)")
        
        logger.success("Format elements parsed", f"{len(self.mesh_buffer_format_elements)} elements")
        return len(self.mesh_buffer_format_elements)



        
    
    
    
    
    
    
    
    
    
    
    
    # --- 4.12: File Mesh Buffer Headers (FIXED) ---
    def read_file_mesh_buffer_headers(self):
        """Parse FILE_MESH_BUFFER_HEADERS (feature 14) - Vertex/Index buffer locations"""
        logger.sub_section("Reading File Mesh Buffer Headers")
        fh = self._get_feature_header(14)  # FILE_MESH_BUFFER_HEADERS
        
        if not fh:
            logger.warning("No FILE_MESH_BUFFER_HEADERS feature (14)")
            return 0
        
        offset = self.header['features_data_offset'] + fh['data_offset']
        count = fh['total_count']
        header_size = 0x10  # 16 bytes per header
        
        # Bounds check
        if offset + count * header_size > len(self.data):
            logger.warning(f"File headers truncated: {count} need {count*header_size} bytes")
            count = (len(self.data) - offset) // header_size
        
        logger.start(f"Reading {count} file buffer headers @ 0x{offset:08X}")
        self.file_mesh_buffer_headers.clear()
        
        for i in range(count):
            file_offset = offset + (i * header_size)
            if file_offset + header_size > len(self.data):
                logger.warning(f"Header {i} truncated")
                break
            
            # ✅ FIXED: Complete 16-byte structure parsing
            buf_type = struct.unpack('<H', self.data[file_offset:file_offset+2])[0]           # 0-1: Buffer type
            padding1 = self.data[file_offset+2:file_offset+4]                                  # 2-3: Padding
            data_size = struct.unpack('<I', self.data[file_offset+4:file_offset+8])[0]        # 4-7: Data size
            data_offset = struct.unpack('<I', self.data[file_offset+8:file_offset+12])[0]     # 8-11: Data offset
            padding2 = self.data[file_offset+12:file_offset+16]                                # 12-15: Padding
            
            # Buffer type mapping (Fox Engine standard)
            type_name = (
                "VERTEX_BUFFER" if buf_type == 0 else
                "INDEX_BUFFER" if buf_type == 1 else
                f"UNKNOWN_{buf_type:04X}"
            )
            
            # Validation
            is_valid = True
            if data_offset + data_size > len(self.data):
                is_valid = False
                logger.warning(f"Buffer {i}: invalid range 0x{data_offset:08X}+0x{data_size:08X}")
            
            self.file_mesh_buffer_headers.append({
                'index': i,
                'type': buf_type,
                'type_name': type_name,
                'data_size': data_size,
                'data_offset': data_offset,
                'file_offset': file_offset,
                'valid': is_valid,
                'padding1': padding1.hex(),
                'padding2': padding2.hex(),
            })
            
            # Detailed logging for first few + invalids
            if i < 5 or not is_valid:
                status = "✓" if is_valid else "✗"
                logger.info(f"[{status}] F{i:2d}: {type_name:<12} "
                           f"size=0x{data_size:06X}B offset=0x{data_offset:08X}")
        
        logger.success("File buffer headers parsed", f"{len(self.file_mesh_buffer_headers)} headers")
        
        # Statistics
        vbuffers = sum(1 for h in self.file_mesh_buffer_headers if h['type_name'] == 'VERTEX_BUFFER')
        ibuffers = sum(1 for h in self.file_mesh_buffer_headers if h['type_name'] == 'INDEX_BUFFER')
        invalid = sum(1 for h in self.file_mesh_buffer_headers if not h['valid'])
        
        logger.info(f"VBuffers: {vbuffers}, IBuffers: {ibuffers}, Invalid: {invalid}")
        return len(self.file_mesh_buffer_headers)

    
    
    
    
    
    
    
    
    
    
    
    # --- 4.13: IBuffer Slices (FIXED & OPTIMIZED) ---
    def read_ibuffer_slices(self):
        """Parse IBUFFER_SLICES (feature 17) - Index buffer sub-ranges for submeshes"""
        logger.sub_section("Reading IBuffer Slices")
        fh = self._get_feature_header(17)  # IBUFFER_SLICES
        
        if not fh:
            logger.warning("No IBUFFER_SLICES feature (17)")
            return 0
        
        offset = self.header['features_data_offset'] + fh['data_offset']
        count = fh['total_count']
        slice_size = 8  # 8 bytes per slice (start_index + count)
        
        # Bounds check
        if offset + count * slice_size > len(self.data):
            logger.warning(f"IBuffer slices truncated: {count} need {count*slice_size} bytes")
            count = (len(self.data) - offset) // slice_size
        
        logger.start(f"Reading {count} IBuffer slices @ 0x{offset:08X}")
        self.ibuffer_slices.clear()
        
        total_indices = 0
        for i in range(count):
            slice_offset = offset + (i * slice_size)
            if slice_offset + slice_size > len(self.data):
                logger.warning(f"Slice {i} truncated")
                break
            
            # ✅ FIXED: Complete 8-byte parsing
            start_index = struct.unpack('<I', self.data[slice_offset:slice_offset+4])[0]      # 0-3: Start index
            index_count = struct.unpack('<I', self.data[slice_offset+4:slice_offset+8])[0]   # 4-7: Triangle count
            
            # Validation
            is_valid = True
            if start_index + index_count > self._get_total_indices():
                is_valid = False
                logger.warning(f"Slice {i}: invalid range {start_index}+{index_count}")
            
            self.ibuffer_slices.append({
                'index': i,
                'start_index': start_index,
                'count': index_count,
                'triangles': index_count // 3,  # Assuming triangles
                'valid': is_valid,
                'offset': slice_offset,
            })
            
            total_indices += index_count
            
            # Log first 10 + invalids
            if i < 10 or not is_valid:
                status = "✓" if is_valid else "✗"
                tris = index_count // 3
                logger.info(f"[{status}] S{i:2d}: start={start_index:8d}, "
                           f"count={index_count:6d} ({tris} triangles)")
        
        logger.success("IBuffer slices parsed", f"{len(self.ibuffer_slices)} slices")
        
        # Statistics
        valid_slices = sum(1 for s in self.ibuffer_slices if s['valid'])
        total_tris = sum(s['count'] // 3 for s in self.ibuffer_slices)
        
        logger.info(f"Valid: {valid_slices}/{len(self.ibuffer_slices)}, "
                    f"Total triangles: {total_tris}")
        
        return len(self.ibuffer_slices)

    def _get_total_indices(self):
        """Helper: Get total available indices from index buffers"""
        total = 0
        for h in self.file_mesh_buffer_headers:
            if h['type_name'] == 'INDEX_BUFFER':
                total += h['data_size'] // 2  # Assuming 16-bit indices
        return total

        
    
    
    
    # --- 4.14: Vertex Buffer Data (UNIVERSAL) ---
    def read_vertex_buffers(self):
        """Parse ALL Vertex Buffers - Dynamic LOD detection"""
        logger.sub_section("Reading Vertex Buffers (Universal)")
        
        vbuffers = [h for h in self.file_mesh_buffer_headers if h.get('type_name') == 'VERTEX_BUFFER']
        if not vbuffers:
            logger.warning("No VERTEX_BUFFER headers found")
            return 0
        
        self.vertex_buffers = []
        logger.start(f"Found {len(vbuffers)} VBuffers")
        
        for vbuf_idx, vbuf in enumerate(vbuffers):
            # Dynamic format matching
            format_elements = self._get_format_for_vbuffer(vbuf_idx)
            stride = self._calculate_stride(format_elements)
            vertex_count = vbuf['data_size'] // stride if stride > 0 else 0
            
            # Parse sample vertices (first 100 for bounds)
            sample_vertices = self._parse_vbuffer_sample(vbuf, format_elements, stride, 100)
            
            self.vertex_buffers.append({
                'index': vbuf_idx,
                'lod_level': vbuf_idx,
                'header': vbuf,
                'format_elements': format_elements,
                'stride': stride,
                'vertex_count': vertex_count,
                'sample_vertices': sample_vertices,
                'bounds': self._calculate_bounds(sample_vertices)
            })
            
            logger.info(f"VBuf{vbuf_idx}: {vertex_count:,} verts, stride={stride}B")
        
        logger.success("Vertex buffers parsed", f"{len(self.vertex_buffers)} buffers")
        return len(self.vertex_buffers)

    # --- 4.15: AABBs (UNIVERSAL - قبلاً OK) ---
    def read_aabbs(self):
        """Parse AABBS feature dynamically"""
        logger.sub_section("Reading AABBs")
        fh = self._get_feature_header_by_name(b'AABB') or self._get_feature_header_by_name(b'BOUND')
        
        if not fh:
            logger.warning("No AABB feature found")
            return 0
        
        offset = self.header['features_data_offset'] + fh['data_offset']
        count = fh['total_count']
        aabb_size = 0x20
        
        if offset + count * aabb_size > len(self.data):
            count = (len(self.data) - offset) // aabb_size
        
        logger.start(f"Reading {count} AABBs @ 0x{offset:08X}")
        self.aabbs.clear()
        
        for i in range(count):
            aabb_offset = offset + (i * aabb_size)
            if aabb_offset + aabb_size > len(self.data): break
            
            min_xyz = struct.unpack('<3f', self.data[aabb_offset:aabb_offset+12])
            max_xyz = struct.unpack('<3f', self.data[aabb_offset+16:aabb_offset+28])
            
            center = [(min_xyz[j] + max_xyz[j]) / 2 for j in range(3)]
            size = [max_xyz[j] - min_xyz[j] for j in range(3)]
            
            self.aabbs.append({
                'index': i, 'min': min_xyz, 'max': max_xyz,
                'center': tuple(center), 'size': tuple(size)
            })
            
            if i < 10:
                status = "✓" if all(s > 0 for s in size) else "✗"
                logger.info(f"[{status}] A{i:2d}: center=({center[0]:.2f},{center[1]:.2f},{center[2]:.2f})")
        
        logger.success("AABBs parsed", f"{len(self.aabbs)} boxes")
        self._link_aabbs_to_meshes()
        return len(self.aabbs)

    # --- 4.16: Skeleton Hierarchy (UNIVERSAL) ---
    def read_skeleton_hierarchy(self):
        """Find BONE feature dynamically"""
        logger.sub_section("Reading Skeleton Hierarchy")
        bone_fh = self._get_feature_header_by_name(b'BONE') or self._get_feature_header_by_name(b'SKELETON')
        
        if not bone_fh:
            logger.warning("No bone hierarchy feature found")
            return 0
        
        offset = self.header['features_data_offset'] + bone_fh['data_offset']
        count = bone_fh['total_count']
        bone_size = 4  # parent_index
        
        logger.start(f"Reading {count} bones @ 0x{offset:08X}")
        self.bones = []
        
        for i in range(count):
            bone_offset = offset + (i * bone_size)
            if bone_offset + bone_size > len(self.data): break
            
            parent_idx = struct.unpack('<i', self.data[bone_offset:bone_offset+4])[0]
            
            self.bones.append({
                'index': i,
                'parent_index': parent_idx,
                'parent_name': f"Bone_{parent_idx}" if parent_idx >= 0 else "ROOT",
                'name': f"Bone_{i:03d}",  # Will be updated later
                'local_matrix': None,
                'bind_matrix': None
            })
            
            if i < 10:
                logger.info(f"Bone {i:2d} ← Parent {parent_idx}")
        
        logger.success("Skeleton parsed", f"{len(self.bones)} bones")
        return len(self.bones)

    # --- 4.17: Bone Names (UNIVERSAL - Dynamic) ---
    def read_bone_names(self):
        """Dynamic bone name detection for ALL FMDL files"""
        logger.sub_section("Reading Bone Names")
        
        # Strategy 1: Feature با تعداد bone ها
        name_fh = None
        for fh in self.feature_headers:
            if fh['total_count'] == len(self.bones):
                name_fh = fh
                logger.info(f"✓ Bone names: feature {fh.get('id', '?')}")
                break
        
        # Strategy 2: NAME/HASH keywords
        if not name_fh:
            for fh in self.feature_headers:
                name = fh.get('name', b'').decode('ascii', errors='ignore').upper()
                if 'NAME' in name or 'HASH' in name:
                    name_fh = fh
                    logger.info(f"✓ Name feature: {name}")
                    break
        
        if not name_fh:
            logger.warning("No bone names → using indexed fallback")
            for i, bone in enumerate(self.bones):
                bone['name'] = f"Bone_{i:03d}"
            return len(self.bones)
        
        # Parse names
        offset = self.header['features_data_offset'] + name_fh['data_offset']
        for i, bone in enumerate(self.bones):
            name = self._find_bone_name(offset, i, name_fh['total_count'])
            bone['name'] = name or f"Bone_{i:03d}"
            
            if i < 5:
                logger.info(f"Bone {i}: {bone['name']}")
        
        logger.success("Bone names loaded", f"{len(self.bones)} names")
        return len(self.bones)

    # --- 4.18: Bone Transforms (UNIVERSAL) ---
    def read_bone_transforms(self):
        """Dynamic bone matrix detection"""
        logger.sub_section("Reading Bone Transforms")
        
        # Find matrix feature (usually بعد bone hierarchy)
        matrix_fh = None
        for fh in self.feature_headers:
            if fh['total_count'] == len(self.bones) and fh.get('data_offset', 0) > 0x1000:
                matrix_fh = fh
                break
        
        if not matrix_fh:
            logger.warning("No bone transforms found")
            return 0
        
        offset = self.header['features_data_offset'] + matrix_fh['data_offset']
        count = min(matrix_fh['total_count'], len(self.bones))
        matrix_size = 0x40  # 4x4 float matrix
        
        logger.start(f"Reading {count} matrices @ 0x{offset:08X}")
        
        for i in range(count):
            if i >= len(self.bones): break
            matrix_offset = offset + (i * matrix_size)
            if matrix_offset + matrix_size > len(self.data): break
            
            matrix = self._read_matrix4x4(matrix_offset)
            self.bones[i]['local_matrix'] = matrix
            self.bones[i]['bind_matrix'] = matrix.copy()
            
            if i < 3:
                pos = [matrix[j*4] for j in range(3)]  # Extract translation
                logger.info(f"Bone {i} ({self.bones[i]['name']}): pos=({pos[0]:.3f},{pos[1]:.3f},{pos[2]:.3f})")
        
        logger.success("Bone transforms loaded", f"{count} matrices")
        return count

    # --- 4.19: Mesh Buffer Headers (UNIVERSAL) ---
    def read_mesh_buffer_headers(self):
        """Parse MESH_BUFFER_HEADERS dynamically"""
        logger.sub_section("Reading Mesh Buffer Headers")
        fh = self._get_feature_header_by_name(b'MESH_BUFFER_HEADER')
        
        if not fh:
            logger.warning("No MESH_BUFFER_HEADERS feature")
            return 0
        
        offset = self.header['features_data_offset'] + fh['data_offset']
        count = fh['total_count']
        header_size = 0x18
        
        if offset + count * header_size > len(self.data):
            count = (len(self.data) - offset) // header_size
        
        logger.start(f"Reading {count} submeshes @ 0x{offset:08X}")
        self.mesh_buffer_headers.clear()
        
        for i in range(count):
            header_offset = offset + (i * header_size)
            if header_offset + header_size > len(self.data): break
            
            # Safe unpacking with validation
            vertex_count = struct.unpack('<I', self.data[header_offset:header_offset+4])[0]
            index_count = struct.unpack('<I', self.data[header_offset+4:header_offset+8])[0]
            stride = struct.unpack('<H', self.data[header_offset+8:header_offset+10])[0]
            data_layout_idx = struct.unpack('<H', self.data[header_offset+10:header_offset+12])[0]
            vbuffer_idx = struct.unpack('<H', self.data[header_offset+12:header_offset+14])[0]
            ibuffer_idx = struct.unpack('<H', self.data[header_offset+14:header_offset+16])[0]
            material_idx = struct.unpack('<H', self.data[header_offset+16:header_offset+18])[0]
            
            # Validation
            if vertex_count > 100000:
                logger.warning(f"Mesh {i}: capping {vertex_count} → 50000 verts")
                vertex_count = 50000
            
            self.mesh_buffer_headers.append({
                'index': i, 'vertex_count': vertex_count, 'index_count': index_count,
                'stride': stride, 'data_layout_idx': data_layout_idx,
                'vbuffer_idx': vbuffer_idx, 'ibuffer_idx': ibuffer_idx,
                'material_idx': material_idx, 'aabb': None
            })
            
            if i < 5:
                logger.info(f"Submesh {i}: {vertex_count}v {index_count}i mat={material_idx}")
        
        logger.success("Mesh headers parsed", f"{len(self.mesh_buffer_headers)} submeshes")
        return len(self.mesh_buffer_headers)

    # --- 4.20: Materials (FIXED) ---
    def read_materials(self):
        """Parse MATERIALS feature dynamically - FIXED"""
        logger.sub_section("Reading Materials")
        
        # Multiple strategies
        mat_fh = (self._get_feature_header_by_name(b'MATERIAL') or 
                  self._get_feature_header_by_name(b'MAT') or
                  self._get_feature_header_by_name(b'SHADER'))
        
        if not mat_fh:
            logger.warning("No MATERIALS feature → using fallback")
            self.materials = [{'index': i, 'name': f'Mat_{i}'} for i in range(11)]  # From log
            return len(self.materials)
        
        offset = self.header['features_data_offset'] + mat_fh['data_offset']
        count = mat_fh['total_count']
        
        logger.start(f"Reading {count} materials @ 0x{offset:08X}")
        self.materials = []
        
        for i in range(min(count, 50)):  # Safety limit
            mat_offset = offset + (i * 0x8)
            if mat_offset + 8 > len(self.data): break
            
            shader_idx = struct.unpack('<I', self.data[mat_offset:mat_offset+4])[0]
            texture_count = struct.unpack('<I', self.data[mat_offset+4:mat_offset+8])[0]
            
            self.materials.append({
                'index': i,
                'name': f"Material_{i}",
                'shader_index': shader_idx,
                'texture_count': texture_count,
                'textures': []
            })
            
            if i < 3:
                logger.info(f"Mat {i}: shader=0x{shader_idx:08X}, tex={texture_count}")
        
        logger.success("Materials parsed", f"{len(self.materials)} materials")
        return len(self.materials)













# ============================================
# SECTION 5: VERTEX BUFFER READER
# ============================================

class VertexBufferReader:
    def __init__(self, fmdl_data, file_data):
        self.fmdl = fmdl_data
        self.data = file_data
        logger.section("VERTEX BUFFER READER")

    
    def read_vertex_buffer(self, mesh_def):
        logger.start(f"Reading vertex buffer for mesh {mesh_def['index']}")
        
        layout_idx = mesh_def['data_layout_index']
        if layout_idx >= len(self.fmdl['mesh_data_layouts']):
            logger.error("Invalid layout", layout_idx)
            return None
            
        layout = self.fmdl['mesh_data_layouts'][layout_idx]
        
        # First buffer only
        buffer_header_idx = layout['buffer_headers_start'] + 0
        if buffer_header_idx >= len(self.fmdl['mesh_buffer_headers']):
            logger.error("No buffer header", buffer_header_idx)
            return None
            
        buf_header = self.fmdl['mesh_buffer_headers'][buffer_header_idx]
        
        # Stride validation (فقط یکبار!)
        if buf_header['stride'] == 0:
            logger.error("ZERO STRIDE", f"Mesh {mesh_def['index']} stride=0")
            return None
            
        logger.info(f"Mesh {mesh_def['index']}: Layout={layout_idx}, Stride={buf_header['stride']}")
        
        # File buffer
        file_buf_idx = buf_header['file_buffer_index']
        if file_buf_idx >= len(self.fmdl['file_mesh_buffer_headers']):
            logger.error("No file buffer", file_buf_idx)
            return None
            
        file_buf = self.fmdl['file_mesh_buffer_headers'][file_buf_idx]
        if file_buf['type'] != 0:
            logger.error("Not VBUFFER")
            return None
        
        # Read vertices
        verts = self._read_vertices_from_buffer(mesh_def, buf_header, file_buf, layout['format_elements_start'])
        logger.success("Vertex buffer", f"{len(verts)} vertices")
        return verts

  
    def _read_vertices_from_buffer(self, mesh_def, buf_header, file_buf, format_start):
        stride = buf_header['stride']
        
        expected_size = file_buf['data_size']
        real_vert_count = expected_size // stride  # ✅ بر اساس buffer size
        logger.info(f"Expected: {mesh_def['vertex_count']}, Real: {real_vert_count}")
        vert_count = min(mesh_def['vertex_count'], real_vert_count)
        
        vert_start = mesh_def['vertices_start_index']
        
        # Calculate offset in file
        buffer_start = file_buf['data_offset']
        vert_offset = buffer_start + (vert_start * stride)
        
        # 🔥 log اضافه کن ببین از کجا میخونه:
        logger.info(f"Mesh {mesh_def['index']}: vert_start={vert_start}, offset=0x{vert_offset:X}")
        
        logger.debug(f"Reading {vert_count} vertices from offset 0x{vert_offset:X}, stride={stride}")
        
        logger.info(f"🔍 Mesh {mesh_def['index']}: vert_start={vert_start}, "
           f"vert_offset=0x{vert_offset:X}, stride={stride}")

        
        
        vertices = []
        
        for v in range(vert_count):
            v_offset = vert_offset + (v * stride)
            vertex = self._parse_vertex(v_offset, stride, format_start, buf_header['format_element_count'])
            vertices.append(vertex)
        
        return vertices
    
   
    def _parse_vertex(self, offset, stride, format_start, element_count):
        vertex = {
            'position': None,
            'normal': None,
            'tangent': None,
            'uv': None,
            'uv2': None,
            'color': None,
            'bone_weights': None,
            'bone_indices': None,
        }
        
        # Read each format element
        for e in range(element_count):
            elem_idx = format_start + e
            if elem_idx >= len(self.fmdl['mesh_buffer_format_elements']):
                continue
            
            elem = self.fmdl['mesh_buffer_format_elements'][elem_idx]
            elem_offset = offset + elem['offset']
            
            usage = elem['usage']
            elem_type = elem['type']
            
            try:
                if usage == 0:  # POSITION
                    vertex['position'] = self._read_vector3(elem_offset, elem_type)
                elif usage == 2:  # NORMAL
                    vertex['normal'] = self._read_vector4(elem_offset, elem_type)
                elif usage == 14:  # TANGENT
                    vertex['tangent'] = self._read_vector4(elem_offset, elem_type)
                elif usage == 8:  # UV0
                    vertex['uv'] = self._read_uv(elem_offset, elem_type)
                elif usage == 9:  # UV1
                    vertex['uv2'] = self._read_uv(elem_offset, elem_type)
                elif usage == 3:  # COLOR
                    vertex['color'] = self._read_color(elem_offset, elem_type)
                elif usage == 1:  # BONE_WEIGHT0
                    vertex['bone_weights'] = self._read_bone_weights(elem_offset, elem_type)
                elif usage == 7:  # BONE_INDEX0
                    vertex['bone_indices'] = self._read_bone_indices(elem_offset, elem_type)
            except Exception as e:
                logger.debug(f"Error reading element {e}: {str(e)}")
        
        return vertex
    
    def _read_vector3(self, offset, elem_type):
        if elem_type == 1:  # R32G32B32_FLOAT
            x = struct.unpack('<f', self.data[offset:offset+4])[0]
            y = struct.unpack('<f', self.data[offset+4:offset+8])[0]
            z = struct.unpack('<f', self.data[offset+8:offset+12])[0]
            return (x, y, z)
        return None
    
    def _read_vector4(self, offset, elem_type):
        if elem_type == 6:  # R16G16B16A16_FLOAT
            # Half-float conversion
            x = self._half_to_float(struct.unpack('<H', self.data[offset:offset+2])[0])
            y = self._half_to_float(struct.unpack('<H', self.data[offset+2:offset+4])[0])
            z = self._half_to_float(struct.unpack('<H', self.data[offset+4:offset+6])[0])
            w = self._half_to_float(struct.unpack('<H', self.data[offset+6:offset+8])[0])
            return (x, y, z, w)
        return None
    
    def _read_uv(self, offset, elem_type):
        if elem_type == 7:  # R16G16_FLOAT
            u = self._half_to_float(struct.unpack('<H', self.data[offset:offset+2])[0])
            v = self._half_to_float(struct.unpack('<H', self.data[offset+2:offset+4])[0])
            return (u, v)
        return None
    
    def _read_color(self, offset, elem_type):
        if elem_type == 8:  # R8G8B8A8_UNORM
            r = self.data[offset] / 255.0
            g = self.data[offset+1] / 255.0
            b = self.data[offset+2] / 255.0
            a = self.data[offset+3] / 255.0
            return (r, g, b, a)
        return None
    
    def _read_bone_weights(self, offset, elem_type):
        if elem_type == 8:  # R8G8B8A8_UNORM
            w0 = self.data[offset] / 255.0
            w1 = self.data[offset+1] / 255.0
            w2 = self.data[offset+2] / 255.0
            w3 = self.data[offset+3] / 255.0
            return (w0, w1, w2, w3)
        return None
    
    def _read_bone_indices(self, offset, elem_type):
        if elem_type == 9:  # R8G8B8A8_UINT
            i0 = self.data[offset]
            i1 = self.data[offset+1]
            i2 = self.data[offset+2]
            i3 = self.data[offset+3]
            return (i0, i1, i2, i3)
        return None
    
    def _half_to_float(self, half_val):
        """Convert 16-bit half-float to 32-bit float"""
        import math
        
        sign = (half_val >> 15) & 0x1
        exponent = (half_val >> 10) & 0x1F
        mantissa = half_val & 0x3FF
        
        if exponent == 0:
            if mantissa == 0:
                return -0.0 if sign else 0.0
            else:
                # Subnormal number
                return ((-1) ** sign) * (mantissa / 1024.0) * (2 ** -14)
        elif exponent == 31:
            if mantissa == 0:
                return float('-inf') if sign else float('inf')
            else:
                return float('nan')
        
        # Normal number
        return ((-1) ** sign) * (1.0 + mantissa / 1024.0) * (2 ** (exponent - 15))

# ============================================
# SECTION 6: INDEX BUFFER READER 
# ============================================

class IndexBufferReader:
    def __init__(self, fmdl_data, file_data):
        self.fmdl = fmdl_data
        self.data = file_data
        logger.section("INDEX BUFFER READER")
    
    
    
    def read_faces(self, mesh_def):
        logger.start(f"Reading faces for mesh {mesh_def['index']}")
        
        slice_start = mesh_def['ibuffer_slices_start']
        index_buffer = next((b for b in self.fmdl['file_mesh_buffer_headers'] if b['type'] == 1), None)
        
        if not index_buffer:
            return []
        
        faces = []
        vert_count = mesh_def['vertex_count']
        
        # 🔥 FIXX: همه slices این mesh (تا 4 تا)
        for slice_offset in range(4):  # معمولاً max 4 slices per mesh
            slice_idx = slice_start + slice_offset
            if slice_idx >= len(self.fmdl['ibuffer_slices']):
                break
                
            slice_data = self.fmdl['ibuffer_slices'][slice_idx]
            logger.debug(f"Slice {slice_idx}: start={slice_data['start_index']}, "
                        f"count={slice_data['count']}")
            
            offset = index_buffer['data_offset'] + (slice_data['start_index'] * 2)
            triangle_count = slice_data['count'] // 3
            
            slice_faces = 0
            for i in range(triangle_count):
                if offset + 6 > len(self.data):
                    break
                    
                i0 = struct.unpack('<H', self.data[offset:offset+2])[0]
                i1 = struct.unpack('<H', self.data[offset+2:offset+4])[0]
                i2 = struct.unpack('<H', self.data[offset+4:offset+6])[0]
               
                if (i0 < 65000 and i1 < 65000 and i2 < 65000):  # 16-bit max
                    faces.append((i0, i1, i2))
                    slice_faces += 1
                
                offset += 6
            
            logger.debug(f"Slice {slice_idx}: {slice_faces}/{triangle_count}F")
        
        logger.success(f"Mesh {mesh_def['index']}", f"{len(faces)}F from slices {slice_start}+")
        return faces


















# ============================================
# SECTION 7: MATERIAL SYSTEM 
# ============================================

# --- 7.1: Texture Finder ---

class FoxTextureFinder:
    def __init__(self, texture_folder, fmdl_name, paths_dict):
        self.folder = Path(texture_folder)
        self.fmdl_name = Path(fmdl_name).stem
        self.paths = paths_dict  # From FMDL parser
        self.cache = {}
        
        # Parse FMDL name: qui3_main0_def -> base=qui3, part=main0, variant=def
        parts = self.fmdl_name.split('_')
        self.base_code = parts[0] if len(parts) > 0 else ""
        self.part_name = parts[1] if len(parts) > 1 else ""
        self.variant = parts[2] if len(parts) > 2 else "def"
        
        logger.section("FOX TEXTURE FINDER")
        logger.info(f"FMDL parsed: base={self.base_code}, part={self.part_name}, variant={self.variant}")
        
        # Scan folder
        self._scan_folder()
    
    def _scan_folder(self):
        logger.start("Scanning texture folder")
        self.all_textures = list(self.folder.rglob("*.dds"))
        logger.success("Folder scanned", f"{len(self.all_textures)} DDS files found")
        
        # Build index by base code
        self.index = {}
        for tex in self.all_textures:
            name = tex.stem
            base_match = self._extract_base_code(name)
            if base_match:
                if base_match not in self.index:
                    self.index[base_match] = []
                self.index[base_match].append(tex)
        
        logger.debug(f"Indexed {len(self.index)} base codes")
    
    def _extract_base_code(self, filename):
        parts = filename.split('_')
        return parts[0] if parts else None
    
    def find_texture(self, texture_ref):
        """Find texture by reference from FMDL"""
        cache_key = f"{texture_ref['name_index']}_{texture_ref['path_index']}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Try path from FMDL first
        if texture_ref['path_index'] < len(self.paths):
            path = self.paths[texture_ref['path_index']]['path']
            result = self._find_by_path(path)
            if result:
                self.cache[cache_key] = result
                logger.debug(f"Found by path: {path} -> {result}")
                return result
        
        # Fallback to name guessing
        if texture_ref['name_index'] < len(self.fmdl['names']):
            name = self.fmdl['names'][texture_ref['name_index']]['name']
            result = self._find_by_name(name)
            if result:
                self.cache[cache_key] = result
                logger.debug(f"Found by name: {name} -> {result}")
                return result
        
        self.cache[cache_key] = None
        return None
    
    def _find_by_path(self, full_path):
        """Find texture by full path from dictionary"""
        # Extract filename from path
        filename = Path(full_path).name.replace('.ftex', '.dds')
        
        # Try exact match
        for tex in self.all_textures:
            if tex.name.lower() == filename.lower():
                return tex
        
        # Try partial match
        base_name = filename.replace('.dds', '')
        for tex in self.all_textures:
            if base_name.lower() in tex.name.lower():
                return tex
        
        return None
    
    def _find_by_name(self, name):
        """Find texture by guessing from FMDL name"""
        # Build patterns
        patterns = [
            f"{self.base_code}_{self.part_name}_{self.variant}_{name}*.dds",
            f"{self.base_code}_{self.part_name}_{name}*.dds",
            f"{self.base_code}_{name}*.dds",
            f"*{name}*.dds",
        ]
        
        for pattern in patterns:
            matches = list(self.folder.glob(pattern))
            if matches:
                return matches[0]
        
        return None

# --- 7.2: Material Presets (از XML) ---

class FoxMaterialPresets:
    def __init__(self):
        self.presets = {}
        logger.section("FOX MATERIAL PRESETS")
        self._load_presets()
    
    def _load_presets(self):
        logger.start("Loading presets from XML data")
        
        # Embedded presets from FMDL-Studio-v2 presets.xml (MGS V + GZ + PES + SSD)
        preset_data = self._get_preset_xml()
        
        try:
            root = ET.fromstring(preset_data)
            
            for preset_elem in root.findall('preset'):
                name = preset_elem.get('name', '')
                shader = preset_elem.get('shader', '')
                technique = preset_elem.get('technique', '')
                
                textures = []
                for tex_elem in preset_elem.find('textures'):
                    if tex_elem.tag == 'texture':
                        textures.append({
                            'name': tex_elem.get('name', ''),
                            'type': tex_elem.get('type', ''),
                            'suffix': self._get_suffix_from_type(tex_elem.get('type', '')),
                        })
                
                vectors = []
                for vec_elem in preset_elem.find('vectors'):
                    if vec_elem.tag == 'vector':
                        vectors.append({
                            'name': vec_elem.get('name', ''),
                            'default': vec_elem.get('default', '0,0,0,0'),
                        })
                
                self.presets[name] = {
                    'shader': shader,
                    'technique': technique,
                    'textures': textures,
                    'vectors': vectors,
                }
                
                logger.debug(f"Loaded preset: {name} ({len(textures)} textures)")
            
            logger.success("Presets loaded", f"{len(self.presets)} presets")
            
        except Exception as e:
            logger.error("Preset loading", str(e))
            self._load_fallback_presets()
    
    def _get_suffix_from_type(self, tex_type):
        """Map texture type to file suffix"""
        suffix_map = {
            'Base_Tex_SRGB': '_bsm',
            'NormalMap_Tex_NRM': '_nrm',
            'SpecularMap_Tex_LIN': '_srm',
            'Translucent_Tex_LIN': '_trm',
            'Layer_Tex_SRGB': '_lym',
            'Detail_Tex_SRGB': '_dtm',
            'LightMap_Tex_SRGB': '_lbm',
            'AlphaMap_Tex_LIN': '_alp',
            'MetalnessMap_Tex_LIN': '_mtl',
        }
        return suffix_map.get(tex_type, '')
    
    def get_preset(self, shader_name):
        """Get preset by shader name"""
        # Exact match
        if shader_name in self.presets:
            return self.presets[shader_name]
        
        # Partial match
        for name, preset in self.presets.items():
            if shader_name.lower() in name.lower():
                return preset
        
        # Default fallback
        return self.presets.get('fox3ddf_blin', {
            'shader': 'fox3ddf_blin',
            'technique': 'fox3DDF_Blin',
            'textures': [
                {'name': 'Base_Tex_SRGB', 'type': 'Base_Tex_SRGB', 'suffix': '_bsm'},
                {'name': 'NormalMap_Tex_NRM', 'type': 'NormalMap_Tex_NRM', 'suffix': '_nrm'},
                {'name': 'SpecularMap_Tex_LIN', 'type': 'SpecularMap_Tex_LIN', 'suffix': '_srm'},
            ],
            'vectors': [],
        })
    
    def _get_preset_xml(self):
        """Return embedded presets.xml content"""
        # This is a condensed version of FMDL-Studio-v2 presets.xml
        # Including MGS V (TPP), GZ, PES, and SSD presets
        
        return """<?xml version="1.0" encoding="utf-8"?>
<presets>
  <!-- MGS V TPP Presets -->
  <preset name="fox3ddf_blin" shader="fox3ddf_blin" technique="fox3DDF_Blin">
    <textures>
      <texture name="Base_Tex_SRGB" type="Base_Tex_SRGB"/>
      <texture name="NormalMap_Tex_NRM" type="NormalMap_Tex_NRM"/>
      <texture name="SpecularMap_Tex_LIN" type="SpecularMap_Tex_LIN"/>
    </textures>
    <vectors>
      <vector name="MatParamIndex_0" default="0,0,0,0"/>
    </vectors>
  </preset>
  
  <preset name="fox3ddf_blin_layer" shader="fox3ddf_blin_layer" technique="fox3DDF_Blin_Layer">
    <textures>
      <texture name="Base_Tex_SRGB" type="Base_Tex_SRGB"/>
      <texture name="NormalMap_Tex_NRM" type="NormalMap_Tex_NRM"/>
      <texture name="SpecularMap_Tex_LIN" type="SpecularMap_Tex_LIN"/>
      <texture name="Layer_Tex_SRGB" type="Layer_Tex_SRGB"/>
      <texture name="Detail_Tex_SRGB" type="Detail_Tex_SRGB"/>
    </textures>
    <vectors>
      <vector name="MatParamIndex_0" default="0,0,0,0"/>
      <vector name="LayerParam" default="1,0,0,0"/>
    </vectors>
  </preset>
  
  <preset name="fox3ddf_blin_translucent" shader="fox3ddf_blin_translucent" technique="fox3DDF_Blin_Translucent">
    <textures>
      <texture name="Base_Tex_SRGB" type="Base_Tex_SRGB"/>
      <texture name="NormalMap_Tex_NRM" type="NormalMap_Tex_NRM"/>
      <texture name="SpecularMap_Tex_LIN" type="SpecularMap_Tex_LIN"/>
      <texture name="Translucent_Tex_LIN" type="Translucent_Tex_LIN"/>
    </textures>
    <vectors>
      <vector name="MatParamIndex_0" default="0,0,0,0"/>
      <vector name="SubsurfaceColor" default="1,0.8,0.6,1"/>
    </vectors>
  </preset>
  
  <preset name="fox3ddf_ggx" shader="fox3ddf_ggx" technique="fox3DDF_GGX">
    <textures>
      <texture name="Base_Tex_SRGB" type="Base_Tex_SRGB"/>
      <texture name="NormalMap_Tex_NRM" type="NormalMap_Tex_NRM"/>
      <texture name="SpecularMap_Tex_LIN" type="SpecularMap_Tex_LIN"/>
      <texture name="MetalnessMap_Tex_LIN" type="MetalnessMap_Tex_LIN"/>
    </textures>
    <vectors>
      <vector name="MatParamIndex_0" default="0,0,0,0"/>
    </vectors>
  </preset>
  
  <preset name="fox3ddf_eye" shader="fox3ddf_eye" technique="fox3DDF_Eye">
    <textures>
      <texture name="Base_Tex_SRGB" type="Base_Tex_SRGB"/>
      <texture name="NormalMap_Tex_NRM" type="NormalMap_Tex_NRM"/>
      <texture name="SpecularMap_Tex_LIN" type="SpecularMap_Tex_LIN"/>
      <texture name="Translucent_Tex_LIN" type="Translucent_Tex_LIN"/>
    </textures>
    <vectors>
      <vector name="MatParamIndex_0" default="0,0,0,0"/>
      <vector name="EyeParam" default="0.5,0,0,0"/>
    </vectors>
  </preset>
  
  <preset name="fox3ddf_hair" shader="fox3ddf_hair" technique="fox3DDF_Hair">
    <textures>
      <texture name="Base_Tex_SRGB" type="Base_Tex_SRGB"/>
      <texture name="NormalMap_Tex_NRM" type="NormalMap_Tex_NRM"/>
      <texture name="SpecularMap_Tex_LIN" type="SpecularMap_Tex_LIN"/>
      <texture name="Translucent_Tex_LIN" type="Translucent_Tex_LIN"/>
      <texture name="Detail_Tex_SRGB" type="Detail_Tex_SRGB"/>
    </textures>
    <vectors>
      <vector name="MatParamIndex_0" default="0,0,0,0"/>
      <vector name="HairParam" default="0.5,0,0,0"/>
    </vectors>
  </preset>
  
  <preset name="fox3ddf_glass" shader="fox3ddf_glass" technique="fox3DDF_Glass">
    <textures>
      <texture name="Base_Tex_SRGB" type="Base_Tex_SRGB"/>
      <texture name="NormalMap_Tex_NRM" type="NormalMap_Tex_NRM"/>
      <texture name="GlassReflection_Tex_SRGB" type="GlassReflection_Tex_SRGB"/>
      <texture name="GlassReflectionMask_Tex_LIN" type="GlassReflectionMask_Tex_LIN"/>
    </textures>
    <vectors>
      <vector name="ReflectionIntensity" default="1,0,0,0"/>
      <vector name="GlassRoughness" default="0,0,0,0"/>
      <vector name="GlassFlatness" default="0,0,0,0"/>
    </vectors>
  </preset>
  
  <preset name="fox3dfw_constant" shader="fox3dfw_constant_srgb_ndr" technique="fox3DFW_ConstantSRGB_NDR">
    <textures>
      <texture name="Base_Tex_SRGB" type="Base_Tex_SRGB"/>
    </textures>
    <vectors>
    </vectors>
  </preset>
</presets>"""
    
    def _load_fallback_presets(self):
        """Load minimal fallback presets if XML fails"""
        logger.warning("Loading fallback presets")
        # Already handled in get_preset default














# --- 7.3: Material Builder ---

class FoxMaterialBuilder:
    def __init__(self, material_name, preset_name, texture_data, texture_folder):
        self.name = material_name
        self.preset = FoxMaterialPresets().get_preset(preset_name)
        self.texture_data = texture_data  # Dict of {role: path}
        self.folder = Path(texture_folder)
        self.mat = None
        
        logger.start(f"Building material: {material_name}")
        logger.debug(f"Using preset: {preset_name}")
        logger.debug(f"Available textures: {list(texture_data.keys())}")
    
    def build(self):
        self._create_material()
        self._setup_nodes()
        self._add_textures()
        self._setup_material_settings()
        
        logger.success("Material built", self.name)
        return self.mat
    
    def _create_material(self):
        self.mat = bpy.data.materials.new(name=self.name)
        self.mat.use_nodes = True
        self.nodes = self.mat.node_tree.nodes
        self.links = self.mat.node_tree.links
        self.nodes.clear()
        
        logger.debug("Created new material with nodes")
    
    def _setup_nodes(self):
        # Output node
        self.output = self.nodes.new('ShaderNodeOutputMaterial')
        self.output.location = (800, 0)
        
        # Principled BSDF
        self.bsdf = self.nodes.new('ShaderNodeBsdfPrincipled')
        self.bsdf.location = (400, 0)
        self.links.new(self.bsdf.outputs['BSDF'], self.output.inputs['Surface'])
        
        
        # ✅ FIXED: Blender 4.0+ compatible inputs
        # Default values
        self.bsdf.inputs['Specular IOR Level'].default_value = 0.5
        self.bsdf.inputs['Roughness'].default_value = 0.5
             
        
        logger.debug("Setup BSDF and output nodes (Blender 4.0+ compatible)")
    
    
    def _add_textures(self):
        x_pos = -600
        y_pos = 300
        
        for tex_info in self.preset['textures']:
            role = tex_info['name']
            suffix = tex_info['suffix']
            
            # Find texture path
            tex_path = self.texture_data.get(role)
            if not tex_path:
                logger.debug(f"No texture for role: {role}")
                continue
            
            if not tex_path.exists():
                logger.warning(f"Texture not found: {tex_path}")
                continue
            
            # Load image
            try:
                img = bpy.data.images.load(str(tex_path))
                colorspace = 'sRGB' if 'SRGB' in role else 'Non-Color'
                img.colorspace_settings.name = colorspace
                
                logger.info(f"Loaded texture: {tex_path.name} ({colorspace})")
            except Exception as e:
                logger.error("Texture load", f"{tex_path}: {str(e)}")
                continue
            
            # Create texture node
            tex_node = self.nodes.new('ShaderNodeTexImage')
            tex_node.image = img
            tex_node.location = (x_pos, y_pos)
            tex_node.label = role
            
            # Connect based on role
            self._connect_texture(role, tex_node)
            
            y_pos -= 200  # Stack vertically
    
    def _connect_texture(self, role, tex_node):
        """Connect texture node to appropriate BSDF socket"""
        
        if role == 'Base_Tex_SRGB':
            self.links.new(tex_node.outputs['Color'], self.bsdf.inputs['Base Color'])
            logger.debug("Connected Base Color")
            
        elif role == 'NormalMap_Tex_NRM':
            # Normal map needs conversion
            normal_map = self.nodes.new('ShaderNodeNormalMap')
            normal_map.location = (-200, -100)
            self.links.new(tex_node.outputs['Color'], normal_map.inputs['Color'])
            self.links.new(normal_map.outputs['Normal'], self.bsdf.inputs['Normal'])
            logger.debug("Connected Normal Map")
            
        elif role == 'SpecularMap_Tex_LIN':
            # SRM: R=Roughness, G=Metallic, B=Specular
            sep = self.nodes.new('ShaderNodeSeparateRGB')
            sep.location = (-200, -300)
            self.links.new(tex_node.outputs['Color'], sep.inputs['Image'])
            
            self.links.new(sep.outputs['R'], self.bsdf.inputs['Roughness'])
            self.links.new(sep.outputs['G'], self.bsdf.inputs['Metallic'])
            logger.debug("Connected SRM (R=Roughness, G=Metallic)")
            
        elif role == 'Translucent_Tex_LIN':
            self.links.new(tex_node.outputs['Color'], self.bsdf.inputs['Subsurface Color'])
            self.bsdf.inputs['Subsurface'].default_value = 0.1
            logger.debug("Connected Subsurface")
            
        elif role == 'LightMap_Tex_SRGB':
            self.links.new(tex_node.outputs['Color'], self.bsdf.inputs['Emission'])
            logger.debug("Connected Emission")
            
        elif role == 'AlphaMap_Tex_LIN':
            self.links.new(tex_node.outputs['Color'], self.bsdf.inputs['Alpha'])
            self.mat.blend_method = 'BLEND'
            logger.debug("Connected Alpha (Blend mode)")
    
    def _setup_material_settings(self):
        """Set material settings based on preset"""
        preset_name = self.preset.get('shader', '')
        
        # Alpha blend for certain shaders
        if 'glass' in preset_name or 'hair' in preset_name or 'alpha' in preset_name:
            self.mat.blend_method = 'BLEND'
            self.mat.shadow_method = 'CLIP'
            logger.debug("Set blend mode: BLEND")
        
        # Two-sided for hair
        if 'hair' in preset_name:
            self.mat.use_backface_culling = False
            logger.debug("Set two-sided: True")
        
        # Subsurface for skin/eye
        if 'translucent' in preset_name or 'eye' in preset_name:
            self.bsdf.inputs['Subsurface'].default_value = 0.1
            if 'eye' in preset_name:
                self.bsdf.inputs['Roughness'].default_value = 0.0
            logger.debug("Set subsurface settings")

# ============================================
# SECTION 8: BLENDER BUILDER (تکمیل شده)
# ============================================

class BlenderBuilder:
    def __init__(self, fmdl_data, texture_folder):
        self.data = fmdl_data
        self.texture_folder = texture_folder
        self.created_materials = {}
        self.armature = None
        self.aabb_empties = []
        
        logger.section("BLENDER BUILDER INITIALIZED")
        logger.info(f"Input data: {len(self.data['bones'])} bones, "
                   f"{len(self.data['meshes'])} meshes, "
                   f"{len(self.data['materials'])} materials")
    
    # --- 8.1: Armature Builder ---
    def create_armature(self):
        if not self.data['bones']:
            logger.info("No bones to create")
            return None
        
        logger.sub_section("Creating Armature")
        logger.start(f"Creating armature with {len(self.data['bones'])} bones")
        
        # Create armature data and object
        armature_data = bpy.data.armatures.new(name="FMDL_Armature_Data")
        self.armature = bpy.data.objects.new(name="FMDL_Armature", object_data=armature_data)
        bpy.context.collection.objects.link(self.armature)
        
        # Enter edit mode
        bpy.context.view_layer.objects.active = self.armature
        bpy.ops.object.mode_set(mode='EDIT')
        
        edit_bones = armature_data.edit_bones
        bone_lookup = {}
        
        # First pass: create all bones
        for bone_data in self.data['bones']:
            bone_name = bone_data.get('name', f"Bone_{bone_data['index']}")
            
            # Get world position
            pos_data = bone_data.get('world_position', (0, 0, 0))
            
            # Convert Y-up to Z-up: (x, y, z) -> (x, z, -y)
            pos = Vector((pos_data[0], pos_data[2], -pos_data[1]))
            
            bone = edit_bones.new(bone_name)
            bone.head = pos
            bone.tail = pos + Vector((0, 0.1, 0))  # Default tail
            bone_lookup[bone_data['index']] = bone
            
            logger.debug(f"Created bone: {bone_name} at ({pos.x:.3f}, {pos.y:.3f}, {pos.z:.3f})")
        
        # Second pass: set parents
        for bone_data in self.data['bones']:
            if bone_data['parent'] >= 0:
                bone = bone_lookup[bone_data['index']]
                parent = bone_lookup.get(bone_data['parent'])
                if parent:
                    bone.parent = parent
                    logger.debug(f"Set parent: {bone.name} -> {parent.name}")
        
        # Third pass: adjust tails based on children
        for bone in edit_bones:
            children = [b for b in edit_bones if b.parent == bone]
            if children:
                avg = sum((c.head for c in children), Vector()) / len(children)
                bone.tail = avg
                logger.debug(f"Adjusted tail for {bone.name} based on {len(children)} children")
        
        # Exit edit mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        logger.success("Armature created", f"{len(self.data['bones'])} bones")
        return self.armature
    
    # --- 8.2: AABB Builder (دو حالته) ---
    def create_aabbs(self, mode='all'):
        """
        Create AABB visualization empties
        mode='all': Create for all AABBs
        mode='important': Create only for root bones (parent=-1)
        """
        if not self.data['aabbs']:
            logger.info("No AABBs to create")
            return
        
        logger.sub_section(f"Creating AABBs (mode: {mode})")
        
        aabbs_to_create = []
        
        if mode == 'all':
            aabbs_to_create = list(enumerate(self.data['aabbs']))
            logger.start(f"Creating all {len(aabbs_to_create)} AABBs")
        elif mode == 'important':
            # Only for root bones
            for bone in self.data['bones']:
                if bone['parent'] == -1 and bone['aabb_index'] < len(self.data['aabbs']):
                    aabbs_to_create.append((bone['aabb_index'], self.data['aabbs'][bone['aabb_index']]))
            logger.start(f"Creating {len(aabbs_to_create)} important AABBs (root bones)")
        else:
            logger.warning(f"Unknown AABB mode: {mode}")
            return
        
        for idx, aabb in aabbs_to_create:
            # Calculate dimensions
            size = aabb['size']
            center = aabb['center']
            
            # Convert center to Z-up
            center_zup = (center[0], center[2], -center[1])
            
            # Create empty
            empty = bpy.data.objects.new(
                name=f"AABB_{idx}",
                object_data=None
            )
            empty.location = center_zup
            empty.empty_display_type = 'CUBE'
            empty.empty_display_size = max(size) / 2 if max(size) > 0 else 0.1
            empty.scale = (size[0]/2, size[2]/2, size[1]/2)  # Swap Y and Z for Z-up
            
            bpy.context.collection.objects.link(empty)
            self.aabb_empties.append(empty)
            
            logger.debug(f"Created AABB {idx}: size=({size[0]:.3f}, {size[1]:.3f}, {size[2]:.3f})")
        
        logger.success("AABBs created", f"{len(self.aabb_empties)} boxes")
    
    # --- 8.3: Mesh Builder ---
    def create_meshes(self):
        logger.sub_section("Creating Meshes")
        logger.start(f"Creating {len(self.data['meshes'])} meshes")
        
        objects = []
        
        for mesh_data in self.data['meshes']:
            obj = self._create_single_mesh(mesh_data)
            if obj:
                objects.append(obj)
        
        logger.success("Meshes created", f"{len(objects)} objects")
        return objects
    
    

    
    
    
    
    
    def _create_single_mesh(self, mesh_data):
        mesh_idx = mesh_data['index']
        
        # Read buffers
        vertex_reader = VertexBufferReader(self.data, self.data.get('raw_data'))
        vertices = vertex_reader.read_vertex_buffer(mesh_data)
        if not vertices or len(vertices) < 6:
            return None
            
        index_reader = IndexBufferReader(self.data, self.data.get('raw_data'))
        faces = index_reader.read_faces(mesh_data)
        
        if len(faces) < 3:
            logger.warning(f"Skip {mesh_idx}: {len(vertices)}V {len(faces)}F")
            return None
        
        # Create mesh
        mesh_name = f"Mesh_{mesh_idx}"
        mesh = bpy.data.meshes.new(mesh_name)
        obj = bpy.data.objects.new(mesh_name, mesh)
        bpy.context.collection.objects.link(obj)
        
        # Build mesh
        bm = bmesh.new()
        vert_map = []
        
        for v_data in vertices:
            pos = v_data.get('position', (0, 0, 0))
            v = bm.verts.new((pos[0], pos[2], -pos[1]))
            vert_map.append(v)
        
        bm.verts.ensure_lookup_table()
        
        # Create faces (SIMPLE VERSION - NO FILTER)
        face_count = 0
        for face_indices in faces[:5000]:  # limit crash
            if len(face_indices) == 3:
                i0, i1, i2 = face_indices
                if 0 <= i0 < len(vert_map) and 0 <= i1 < len(vert_map) and 0 <= i2 < len(vert_map):
                    try:
                        bm.faces.new([vert_map[i0], vert_map[i1], vert_map[i2]])
                        face_count += 1
                    except:
                        pass
        
        bm.normal_update()
        bm.to_mesh(mesh)
        bm.free()
        
        logger.info(f"Mesh {mesh_idx}: {len(vertices)}V {face_count}F created")
        
        # Material
        mat_idx = mesh_data.get('material_index', -1)
        if mat_idx >= 0 and hasattr(self, 'created_materials') and mat_idx < len(self.created_materials):
            obj.data.materials.append(self.created_materials[mat_idx])
        
        logger.success(f"Mesh {mesh_idx}", f"{len(vertices)}V {face_count}F")
        return obj





    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    def _add_weights(self, obj, vertices, mesh_data):
        """Add vertex groups and armature modifier"""
        logger.start("Adding skin weights")
        
        # Get bone group
        bone_group_idx = mesh_data.get('bone_group', 0)
        if bone_group_idx >= len(self.data['bone_groups']):
            return
        
        bone_group = self.data['bone_groups'][bone_group_idx]
        bone_indices = bone_group.get('bone_indices', [])
        
        # Create vertex groups
        for bone_idx in bone_indices:
            if bone_idx < len(self.data['bones']):
                bone_name = self.data['bones'][bone_idx]['name']
                obj.vertex_groups.new(name=bone_name)
                logger.debug(f"Created vertex group: {bone_name}")
        
        # Assign weights
        for v_idx, v_data in enumerate(vertices):
            weights = v_data.get('bone_weights')
            indices = v_data.get('bone_indices')
            
            if weights and indices:
                for w, b_idx in zip(weights, indices):
                    if w > 0.001 and b_idx < len(bone_indices):
                        real_bone_idx = bone_indices[b_idx]
                        if real_bone_idx < len(self.data['bones']):
                            bone_name = self.data['bones'][real_bone_idx]['name']
                            obj.vertex_groups[bone_name].add([v_idx], w, 'REPLACE')
        
        # Add armature modifier
        modifier = obj.modifiers.new(name="Armature", type='ARMATURE')
        modifier.object = self.armature
        modifier.use_vertex_groups = True
        
        logger.success("Weights added")
    
    
    
    
    # --- 8.4: Material Assigner ---
    def create_materials(self):
        logger.sub_section("Creating Materials")
        logger.start(f"Creating {len(self.data['materials'])} materials")
        
        # Initialize presets
        presets = FoxMaterialPresets()
        
        for mat_data in self.data['materials']:
            mat_name = mat_data['name']
            mat_idx = mat_data['index']
            
            logger.start(f"Processing material {mat_idx}: {mat_name}")
            
            # Get shader name from material data or use default
            shader_name = 'fox3ddf_blin'  # Default
            
            # Find texture data for this material
            texture_data = {}
            for tex_ref in mat_data.get('texture_refs', []):
                role = tex_ref.get('name', '')
                # Find actual texture file
                tex_path = self._find_texture_file(tex_ref)
                if tex_path:
                    texture_data[role] = tex_path
                    logger.info(f"Found texture for {role}: {tex_path.name}")
            
            # Build material
            builder = FoxMaterialBuilder(mat_name, shader_name, texture_data, self.texture_folder)
            
    
    
                # در create_materials(), خط builder.build() رو عوض کن:
            try:
                mat = builder.build()
            except Exception as e:
                logger.error(f"Material failed {mat_name}: {e}")
                # Fallback material
                mat = bpy.data.materials.new(name=mat_name)
                mat.use_nodes = True
                bsdf = mat.node_tree.nodes["Principled BSDF"]
                bsdf.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1)
                self.created_materials[mat_idx] = mat
                continue
            
            
            
            self.created_materials[mat_idx] = mat
        logger.success("Materials created", f"{len(self.created_materials)} materials")
    
    
    
    def _find_texture_file(self, tex_ref):
        """Find texture file by reference"""
        # Try path from FMDL
        path_idx = tex_ref.get('path_index', -1)
        if path_idx >= 0 and path_idx < len(self.data['paths']):
            path = self.data['paths'][path_idx]['path']
            # Extract filename
            filename = Path(path).name.replace('.ftex', '.dds')
            
            # Search in texture folder
            for tex_file in Path(self.texture_folder).rglob('*.dds'):
                if tex_file.name.lower() == filename.lower():
                    return tex_file
                if filename.lower() in tex_file.name.lower():
                    return tex_file
        
        return None
    
    def build(self, aabb_mode='all'):
        """Main build function"""
        logger.section("BUILDING BLENDER SCENE")
        
        # Create materials first (needed by meshes)
        self.create_materials()
        
        # Create armature
        self.create_armature()
        
        # Create AABBs (optional, comment out if not needed)
        # mode='all' for all AABBs, mode='important' for root bones only
        self.create_aabbs(mode=aabb_mode)
        
        # Create meshes
        objects = self.create_meshes()
        
        logger.section("BUILD COMPLETE")
        logger.result("Armature", "1" if self.armature else "0")
        logger.result("AABBs", len(self.aabb_empties))
        logger.result("Meshes", len(objects))
        logger.result("Materials", len(self.created_materials))
        
        return self.armature, objects


# ============================================
# SECTION 9: MAIN EXECUTION
# ============================================

def parse_fmdl(filepath, dict_folder):
    """Parse FMDL file and return all data"""
    logger.section("PARSING FMDL FILE")
    
    # Initialize dictionary manager
    dict_manager = DictionaryManager(dict_folder)
    
    # Create parser
    parser = FMDLParser(filepath, dict_manager)
    
    # Store raw data for vertex reading
    parser.data_dict = {'raw_data': parser.data}
    
    # Parse all sections
    parser.read_header()
    parser.read_feature_headers()
    parser.read_buffer_headers()
    parser.read_names()
    parser.read_paths()
    parser.read_bone_defs()
    parser.read_mesh_defs()
    parser.read_materials()
    parser.read_texture_refs()
    parser.read_mesh_data_layouts()
    parser.read_mesh_buffer_headers()
    parser.read_mesh_buffer_format_elements()
    parser.read_file_mesh_buffer_headers()
    parser.read_ibuffer_slices()
    parser.read_aabbs()
    
    # Build result dictionary
    result = {
        'raw_data': parser.data,
        'header': parser.header,
        'feature_headers': parser.feature_headers,
        'buffer_headers': parser.buffer_headers,
        'bones': parser.bones,
        'materials': parser.materials,
        'meshes': parser.meshes,
        'names': parser.names,
        'paths': parser.paths,
        'texture_refs': parser.texture_refs,
        'mesh_data_layouts': parser.mesh_data_layouts,
        'mesh_buffer_headers': parser.mesh_buffer_headers,
        'mesh_buffer_format_elements': parser.mesh_buffer_format_elements,
        'file_mesh_buffer_headers': parser.file_mesh_buffer_headers,
        'ibuffer_slices': parser.ibuffer_slices,
        'aabbs': parser.aabbs,
        'bone_groups': [],  # Will be populated if read
    }
    
    logger.section("PARSING COMPLETE")
    logger.result("Bones", len(result['bones']))
    logger.result("Meshes", len(result['meshes']))
    logger.result("Materials", len(result['materials']))
    logger.result("Vertices (total)", sum(m['vertex_count'] for m in result['meshes']))
    logger.result("Indices (total)", sum(m['index_count'] for m in result['meshes']))
    
    return result


def main():
    logger.section("MGS V FMDL IMPORTER STARTED")
    
   
    # ============================================
    # VALIDATION
    # ============================================
    
    logger.start("Validating paths")
    errors = []
    #paths_ok = True
    
    if not os.path.exists(FMDL_PATH):
        logger.error("FMDL path", f"Not found: {FMDL_PATH}")
        #paths_ok = False
    
    if not os.path.exists(TEXTURE_FOLDER):
        logger.error("Texture folder", f"Not found: {TEXTURE_FOLDER}")
        #paths_ok = False
    
    if not os.path.exists(DICTIONARY_FOLDER):
        logger.error("Dictionary folder", f"Not found: {DICTIONARY_FOLDER}")
        #paths_ok = False
    
    if errors:
        for error in errors:
            logger.error("Validation", error)
        logger.error("Validation", "Please fix paths and try again")
        return
    
    logger.success("Path validation")
    
    # ============================================
    # EXECUTION
    # ============================================
    
    try:
        # Parse FMDL
        fmdl_data = parse_fmdl(FMDL_PATH, DICTIONARY_FOLDER)
        
        # Build in Blender
        builder = BlenderBuilder(fmdl_data, TEXTURE_FOLDER)
        
        # Build scene (change aabb_mode as needed)
        armature, objects = builder.build(aabb_mode=AABB_MODE)
        
        logger.section("IMPORT SUCCESSFUL")
        logger.info(f"Armature: {armature.name if armature else 'None'}")
        logger.info(f"Objects: {[o.name for o in objects]}")
        logger.info(f"Total objects created: {len(objects) + (1 if armature else 0)}")
        
    except Exception as e:
        logger.error("Import failed", str(e))
        import traceback
        traceback.print_exc()


# Run
if __name__ == "__main__":
    main()    
        
        