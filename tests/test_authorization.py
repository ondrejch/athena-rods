#!/usr/bin/env python3
"""
Tests for authorization module (Face and RFID authorization)
"""

import pytest
import sys
import os
import hashlib
from unittest.mock import Mock, patch, MagicMock, mock_open

# Mock hardware dependencies before importing
mock_cv2 = Mock()
mock_face_recognition = Mock()
mock_pickle = Mock()
mock_picamera2 = Mock()
mock_spidev = Mock()
mock_gpiozero = Mock()

sys.modules['cv2'] = mock_cv2
sys.modules['face_recognition'] = mock_face_recognition
sys.modules['pickle'] = mock_pickle
sys.modules['picamera2'] = mock_picamera2
sys.modules['spidev'] = mock_spidev
sys.modules['gpiozero'] = mock_gpiozero

# Mock mfrc522 module at import level
mock_mfrc522_module = Mock()
mock_storemfrc522_class = Mock()
mock_mfrc522_module.StoreMFRC522 = mock_storemfrc522_class
sys.modules['mfrc522'] = mock_mfrc522_module

from arod_control.authorization import FaceAuthorization, RFID_Authorization


class TestFaceAuthorization:
    """Test class for Face Authorization"""

    @pytest.fixture
    def mock_face_data(self):
        """Mock face recognition data"""
        return {
            'encodings': [
                [0.1, 0.2, 0.3],  # Alice's encoding
                [0.4, 0.5, 0.6],  # Bob's encoding
                [0.7, 0.8, 0.9],  # Carol's encoding
            ],
            'names': ['Alice', 'Bob', 'Carol']
        }

    @pytest.fixture
    def mock_picam2_instance(self):
        """Mock Picamera2 instance"""
        mock_instance = Mock()
        mock_picamera2.Picamera2.return_value = mock_instance
        return mock_instance

    def test_face_authorization_init(self, mock_face_data, mock_picam2_instance):
        """Test FaceAuthorization initialization"""
        # Mock file operations
        mock_file_data = b'mock_pickle_data'
        
        with patch('builtins.open', mock_open(read_data=mock_file_data)):
            with patch.object(mock_pickle, 'load', return_value=mock_face_data):
                auth = FaceAuthorization()
        
        # Verify camera initialization
        mock_picamera2.Picamera2.assert_called_once()
        mock_picam2_instance.start.assert_called_once()
        
        # Verify data loaded
        assert auth.data == mock_face_data

    def test_scan_face_known_person(self, mock_face_data, mock_picam2_instance):
        """Test scan_face with known person detection"""
        # Setup mock camera frame
        mock_frame = [[100, 150, 200], [50, 75, 100]]  # Dummy image array
        mock_picam2_instance.capture_array.return_value = mock_frame
        
        # Setup mock CV2 operations
        mock_rgb_frame = [[200, 150, 100], [100, 75, 50]]  # Converted frame
        mock_cv2.cvtColor.return_value = mock_rgb_frame
        
        # Setup mock face detection
        mock_boxes = [(10, 20, 30, 40)]  # One face detected
        mock_encodings = [[0.15, 0.25, 0.35]]  # Encoding close to Alice's
        mock_face_recognition.face_locations.return_value = mock_boxes
        mock_face_recognition.face_encodings.return_value = mock_encodings
        
        # Setup mock comparison - Alice matches
        mock_face_recognition.compare_faces.return_value = [True, False, False]
        
        # Initialize and test
        with patch('builtins.open', mock_open()):
            with patch.object(mock_pickle, 'load', return_value=mock_face_data):
                auth = FaceAuthorization()
        
        result = auth.scan_face()
        
        # Verify correct operations called
        mock_picam2_instance.capture_array.assert_called()
        mock_cv2.cvtColor.assert_called_with(mock_frame, mock_cv2.COLOR_BGR2RGB)
        mock_face_recognition.face_locations.assert_called_with(mock_rgb_frame)
        mock_face_recognition.face_encodings.assert_called_with(mock_rgb_frame, mock_boxes)
        mock_face_recognition.compare_faces.assert_called_with(mock_face_data['encodings'], mock_encodings[0])
        
        # Should return Alice
        assert result == 'Alice'

    def test_scan_face_unknown_person(self, mock_face_data, mock_picam2_instance):
        """Test scan_face with unknown person detection"""
        mock_frame = [[100, 150, 200]]
        mock_picam2_instance.capture_array.return_value = mock_frame
        mock_cv2.cvtColor.return_value = mock_frame
        
        # Setup face detection
        mock_boxes = [(10, 20, 30, 40)]
        mock_encodings = [[0.9, 0.8, 0.7]]  # Different from known encodings
        mock_face_recognition.face_locations.return_value = mock_boxes
        mock_face_recognition.face_encodings.return_value = mock_encodings
        
        # No matches
        mock_face_recognition.compare_faces.return_value = [False, False, False]
        
        with patch('builtins.open', mock_open()):
            with patch.object(mock_pickle, 'load', return_value=mock_face_data):
                auth = FaceAuthorization()
        
        result = auth.scan_face()
        
        assert result == 'Unknown'

    def test_scan_face_no_face_detected(self, mock_face_data, mock_picam2_instance):
        """Test scan_face when no face is detected"""
        mock_frame = [[100, 150, 200]]
        mock_picam2_instance.capture_array.return_value = mock_frame
        mock_cv2.cvtColor.return_value = mock_frame
        
        # No faces detected
        mock_face_recognition.face_locations.return_value = []
        mock_face_recognition.face_encodings.return_value = []
        
        with patch('builtins.open', mock_open()):
            with patch.object(mock_pickle, 'load', return_value=mock_face_data):
                auth = FaceAuthorization()
        
        result = auth.scan_face()
        
        # Should return None when no face detected (based on the method logic)
        assert result is None

    def test_scan_face_multiple_matches(self, mock_face_data, mock_picam2_instance):
        """Test scan_face when multiple people match (picks most frequent)"""
        mock_frame = [[100, 150, 200]]
        mock_picam2_instance.capture_array.return_value = mock_frame
        mock_cv2.cvtColor.return_value = mock_frame
        
        # Setup face detection
        mock_boxes = [(10, 20, 30, 40)]
        mock_encodings = [[0.15, 0.25, 0.35]]
        mock_face_recognition.face_locations.return_value = mock_boxes
        mock_face_recognition.face_encodings.return_value = mock_encodings
        
        # Multiple matches - Alice appears twice, Bob once
        mock_face_recognition.compare_faces.return_value = [True, True, False]  # Alice and Bob match
        
        with patch('builtins.open', mock_open()):
            with patch.object(mock_pickle, 'load', return_value=mock_face_data):
                auth = FaceAuthorization()
        
        result = auth.scan_face()
        
        # Should pick the first match when counts are equal 
        # (based on max(counts, key=counts.get) behavior)
        assert result in ['Alice', 'Bob']  # Either could be returned depending on dict ordering

    def test_face_authorization_destructor(self, mock_face_data, mock_picam2_instance):
        """Test FaceAuthorization destructor cleanup"""
        with patch('builtins.open', mock_open()):
            with patch.object(mock_pickle, 'load', return_value=mock_face_data):
                auth = FaceAuthorization()
        
        # Reset mock call counts before testing destructor
        mock_cv2.destroyAllWindows.reset_mock()
        mock_picam2_instance.close.reset_mock()
        
        # Manually call destructor
        auth.__del__()
        
        # Verify cleanup operations
        mock_cv2.destroyAllWindows.assert_called_once()
        mock_picam2_instance.close.assert_called_once()


class TestRFIDAuthorization:
    """Test class for RFID Authorization"""

    @pytest.fixture
    def mock_ca_fingerprint(self):
        """Mock CA certificate fingerprint"""
        return "12:34:56:78:90:AB:CD:EF"

    @pytest.fixture
    def mock_reader_instance(self):
        """Mock StoreMFRC522 reader instance"""
        mock_instance = Mock()
        mock_storemfrc522_class.return_value = mock_instance
        return mock_instance

    def test_rfid_authorization_init(self, mock_ca_fingerprint, mock_reader_instance):
        """Test RFID_Authorization initialization"""
        with patch('builtins.open', mock_open(read_data=mock_ca_fingerprint)):
            auth = RFID_Authorization()
        
        # Verify fingerprint conversion
        expected_fp = int(mock_ca_fingerprint.replace(':', ''), 16)
        assert auth.fp == expected_fp
        
        # Verify reader initialization
        mock_storemfrc522_class.assert_called_once()
        assert auth.reader == mock_reader_instance
        
        # Verify block addresses configuration
        expected_blocks = {7: [4, 5, 6], 11: [8, 9, 10], 15: [12, 13, 14]}
        assert auth.reader.BLOCK_ADDRESSES == expected_blocks
        assert auth.reader.BLOCK_SLOTS == 9  # 3 blocks * 3 addresses each

    def test_get_digest_calculation(self, mock_ca_fingerprint, mock_reader_instance):
        """Test get_digest calculates correct hash"""
        with patch('builtins.open', mock_open(read_data=mock_ca_fingerprint)):
            auth = RFID_Authorization()
        
        test_tag_id = 12345
        
        # Calculate expected digest manually
        n = test_tag_id * auth.fp
        n_bytes = (n.bit_length() + 7) // 8
        n_to_hash = n.to_bytes(n_bytes, byteorder='big')
        hash_obj = hashlib.sha3_512()
        hash_obj.update(n_to_hash)
        expected_digest = hash_obj.hexdigest()
        
        result = auth.get_digest(test_tag_id)
        
        assert result == expected_digest

    def test_get_digest_string_tag_id(self, mock_ca_fingerprint, mock_reader_instance):
        """Test get_digest with string tag ID"""
        with patch('builtins.open', mock_open(read_data=mock_ca_fingerprint)):
            auth = RFID_Authorization()
        
        # Should work with string tag ID
        result1 = auth.get_digest("12345")
        result2 = auth.get_digest(12345)
        
        assert result1 == result2

    def test_get_digest_overflow_check(self, mock_ca_fingerprint, mock_reader_instance):
        """Test get_digest overflow assertion"""
        with patch('builtins.open', mock_open(read_data=mock_ca_fingerprint)):
            auth = RFID_Authorization()
        
        # This should not raise an assertion error for normal values
        test_tag_id = 12345
        auth.get_digest(test_tag_id)  # Should complete without assertion

    def test_read_tag(self, mock_ca_fingerprint, mock_reader_instance):
        """Test read_tag method"""
        with patch('builtins.open', mock_open(read_data=mock_ca_fingerprint)):
            auth = RFID_Authorization()
        
        # Mock reader response
        mock_reader_instance.read.return_value = (12345, "  test_data  ")
        
        tag_id, text = auth.read_tag()
        
        # Verify reader called
        mock_reader_instance.read.assert_called_once()
        
        # Verify results
        assert tag_id == 12345
        assert text == "test_data"  # Should be stripped

    def test_read_tag_with_print(self, mock_ca_fingerprint, mock_reader_instance, capsys):
        """Test read_tag with printing enabled"""
        with patch('builtins.open', mock_open(read_data=mock_ca_fingerprint)):
            auth = RFID_Authorization()
        
        auth.do_print = True
        mock_reader_instance.read.return_value = (67890, "hash_data")
        
        tag_id, text = auth.read_tag()
        
        # Verify output
        captured = capsys.readouterr()
        assert "Hold a tag near the reader" in captured.out
        assert "ID: 67890" in captured.out
        assert "Text: hash_data" in captured.out

    def test_auth_tag_success(self, mock_ca_fingerprint, mock_reader_instance):
        """Test auth_tag with correct digest"""
        with patch('builtins.open', mock_open(read_data=mock_ca_fingerprint)):
            auth = RFID_Authorization()
        
        test_tag_id = 11111
        expected_digest = auth.get_digest(test_tag_id)
        
        # Mock read_tag to return correct data
        with patch.object(auth, 'read_tag', return_value=(test_tag_id, expected_digest)):
            result = auth.auth_tag()
        
        assert result is True

    def test_auth_tag_failure(self, mock_ca_fingerprint, mock_reader_instance):
        """Test auth_tag with incorrect digest"""
        with patch('builtins.open', mock_open(read_data=mock_ca_fingerprint)):
            auth = RFID_Authorization()
        
        test_tag_id = 22222
        wrong_digest = "wrong_digest_data"
        
        # Mock read_tag to return wrong data
        with patch.object(auth, 'read_tag', return_value=(test_tag_id, wrong_digest)):
            result = auth.auth_tag()
        
        assert result is False

    def test_auth_tag_empty_tag(self, mock_ca_fingerprint, mock_reader_instance):
        """Test auth_tag with empty tag"""
        with patch('builtins.open', mock_open(read_data=mock_ca_fingerprint)):
            auth = RFID_Authorization()
        
        # Mock read_tag to return empty data
        with patch.object(auth, 'read_tag', return_value=(12345, "")):
            result = auth.auth_tag()
        
        assert result is False  # Empty string won't match valid digest

    def test_write_tag(self, mock_ca_fingerprint, mock_reader_instance):
        """Test write_tag method"""
        with patch('builtins.open', mock_open(read_data=mock_ca_fingerprint)):
            auth = RFID_Authorization()
        
        test_tag_id = 33333
        expected_digest = auth.get_digest(test_tag_id)
        
        # Mock read_tag to return tag ID
        with patch.object(auth, 'read_tag', return_value=(test_tag_id, "current_data")):
            auth.write_tag()
        
        # Verify writer called with correct digest
        mock_reader_instance.write.assert_called_once_with(expected_digest)

    def test_fingerprint_file_not_found(self, mock_reader_instance):
        """Test initialization when CA fingerprint file not found"""
        with patch('builtins.open', side_effect=FileNotFoundError):
            with pytest.raises(FileNotFoundError):
                RFID_Authorization()

    def test_different_fingerprints_different_digests(self, mock_reader_instance):
        """Test that different fingerprints produce different digests"""
        fp1 = "11:22:33:44:55:66"
        fp2 = "AA:BB:CC:DD:EE:FF"
        
        with patch('builtins.open', mock_open(read_data=fp1)):
            auth1 = RFID_Authorization()
        
        with patch('builtins.open', mock_open(read_data=fp2)):
            auth2 = RFID_Authorization()
        
        test_tag_id = 12345
        digest1 = auth1.get_digest(test_tag_id)
        digest2 = auth2.get_digest(test_tag_id)
        
        # Should be different
        assert digest1 != digest2

    def test_same_tag_id_consistent_digest(self, mock_ca_fingerprint, mock_reader_instance):
        """Test that same tag ID always produces same digest"""
        with patch('builtins.open', mock_open(read_data=mock_ca_fingerprint)):
            auth = RFID_Authorization()
        
        test_tag_id = 98765
        digest1 = auth.get_digest(test_tag_id)
        digest2 = auth.get_digest(test_tag_id)
        
        assert digest1 == digest2

    def test_digest_is_128_chars(self, mock_ca_fingerprint, mock_reader_instance):
        """Test that digest is 128 characters (SHA3-512 hex)"""
        with patch('builtins.open', mock_open(read_data=mock_ca_fingerprint)):
            auth = RFID_Authorization()
        
        test_tag_id = 55555
        digest = auth.get_digest(test_tag_id)
        
        # SHA3-512 produces 64 bytes = 128 hex characters
        assert len(digest) == 128
        assert all(c in '0123456789abcdef' for c in digest.lower())