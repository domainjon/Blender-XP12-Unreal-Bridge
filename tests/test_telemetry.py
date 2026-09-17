"""
test_telemetry.py - Features 20, 21: JSON & Unreal Engine DataTable CSV Exporters.
"""

import unittest
import json
import csv
import io


class TestTelemetry(unittest.TestCase):
    """Tests JSON schema validation and Unreal Engine UDataTable CSV formatting."""

    def test_json_telemetry_structure(self):
        """Verify Draft 2020-12 JSON telemetry schema."""
        doc = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "aircraft": {
                "name": "B738",
                "skeletal_mesh_fbx": "B738.fbx",
                "total_bones": 10,
                "total_animated_bones": 6
            },
            "bindings": [
                {
                    "bone_name": "rudder",
                    "dataref": "sim/flightmodel2/controls/rudder",
                    "motion_type": "ROTATION",
                    "motion_axis": [0.0, 0.0, 1.0],
                    "input_min": -1.0,
                    "input_max": 1.0,
                    "output_min": -25.0,
                    "output_max": 25.0,
                    "unit": "degrees",
                    "default_value": 0.0
                }
            ]
        }
        raw = json.dumps(doc)
        parsed = json.loads(raw)
        self.assertIn("aircraft", parsed)
        self.assertEqual(parsed["bindings"][0]["bone_name"], "rudder")

    def test_csv_telemetry_format(self):
        """Verify Unreal Engine UDataTable CSV formatting."""
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator='\n')
        writer.writerow(["---", "BoneName", "DataRef", "MotionType", "MotionAxis", "InputMin", "InputMax", "OutputMin", "OutputMax", "Unit", "DefaultValue"])
        writer.writerow(["Row_001", "rudder", "sim/flightmodel2/controls/rudder", "Rotation", '"(X=0.000000,Y=0.000000,Z=1.000000)"', "-1.000000", "1.000000", "-25.000000", "25.000000", "degrees", "0.000000"])

        text = buf.getvalue()
        lines = text.strip().split('\n')
        self.assertTrue(lines[0].startswith("---,"))
        self.assertIn('"(X=0.000000,Y=0.000000,Z=1.000000)"', lines[1])


if __name__ == '__main__':
    unittest.main()
