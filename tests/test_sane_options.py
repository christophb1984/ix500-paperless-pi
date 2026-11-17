"""Native option contract tests; descriptors follow the python-sane tuple API."""
import sys
import json
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import control as c
import sane_options as so

class NativeOptionHandle:
    def __init__(self,device): self.device=device
    def get_option(self,index):
        name=next(row[1] for row in self.device.get_options() if row[0]==index)
        values=getattr(self.device,'native_values',{})
        if name in values: return values[name]
        return getattr(self.device,name.replace('-','_'))

class FakeDevice:
    def __init__(self):
        self.source='ADF Duplex';self.mode='Color';self.resolution=200
        self.contrast=0;self.custom_gamma=False;self.gamma_table=[0,64,128,255]
        self.scan=False;self.swskip=0
        self.dev=NativeOptionHandle(self)
    def close(self): pass
    def get_options(self):
        return [(1,'source','Quelle','Quelle',3,0,32,5,['ADF Duplex','ADF Front','ADF Back']),
                (2,'mode','Modus','Modus',3,0,32,5,['Color','Gray','Lineart']),
                (3,'resolution','Auflösung','dpi',1,4,4,5,(100,600,1)),
                (4,'contrast','Kontrast','Kontrast',1,0,4,5,(-127,127,1)),
                (5,'custom-gamma','Gamma anpassen','Gamma einschalten',0,0,4,5,None),
                (6,'gamma-table','Gamma-Tabelle','4 Werte',1,0,16,5 if self.custom_gamma else 37,(0,255,1)),
                (7,'scan','Taste','Hardwaretaste',0,0,4,4,None),
                (8,'swskip','Leerseiten','Backendfilter',2,5,4,5,(0.,100.,0.))]


class QuantizedGeometryDevice(FakeDevice):
    """SANE fixed-point millimetre steps, as opposed to integer UI millimetres."""
    GEOMETRY={'page_width','page_height','tl_x','tl_y','br_x','br_y'}
    def __init__(self):
        super().__init__()
        for name in self.GEOMETRY: setattr(self,name,0.)
    def __setattr__(self,name,value):
        if name in self.GEOMETRY:
            # Emulate SANE's inexact-value handling at native fixed-point precision.
            value=round(value/0.0211639404296875)*0.0211639404296875
        super().__setattr__(name,value)
    def get_options(self):
        rows=super().get_options()
        for i,name in enumerate(('page-width','page-height','tl-x','tl-y','br-x','br-y'),20):
            limit=216. if name in ('page-width','tl-x','br-x') else 356.
            rows.append((i,name,name,'Scan geometry',2,3,4,5,(0.,limit,0.0211639404296875)))
        return rows


class DynamicGeometryDevice(QuantizedGeometryDevice):
    """ADF scan-area bounds follow the backend-rounded physical page size."""
    def get_options(self):
        result=[]
        for row in super().get_options():
            if row[1] in ('br-x','br-y'):
                extent=self.page_width if row[1]=='br-x' else self.page_height
                row=(*row[:8],(0.,extent,0.0211639404296875))
            result.append(row)
        return result

class MethodCollisionDevice(FakeDevice):
    def __init__(self):
        super().__init__()
        del self.scan
        self.native_values={'scan':False,'start':True,'cancel':False}
    def scan(self): raise AssertionError('Reading an option must never start a scan.')
    def start(self): raise AssertionError('Reading an option must never invoke a device action.')
    def cancel(self): raise AssertionError('Reading an option must never invoke a device action.')
    def get_options(self):
        return super().get_options()+[(9,'start','Start','Sensor',0,0,4,4,None),(10,'cancel','Cancel','Sensor',0,0,4,4,None)]

class SaneOptionTests(unittest.TestCase):
    def test_method_named_options_return_native_values_and_serialize(self):
        device=MethodCollisionDevice()
        self.assertTrue(callable(device.scan))
        options=so.apply_profile(device,c.profile_from_config({}))
        serialized=json.loads(json.dumps(options))
        by_name={o['name']:o for o in serialized}
        self.assertIs(by_name['scan']['value'],False)
        self.assertIs(by_name['start']['value'],True)
        self.assertIs(by_name['cancel']['value'],False)
        self.assertFalse(by_name['scan']['editable'])
    def test_real_descriptor_schema_preserves_ranges_inactivity_and_read_only(self):
        options={o['name']:o for o in so.describe_options(FakeDevice())}
        self.assertEqual(options['contrast']['range'],[-127,127,1])
        self.assertFalse(options['gamma-table']['active'])
        self.assertEqual(options['gamma-table']['count'],4)
        self.assertFalse(options['scan']['editable'])
        self.assertFalse(options['swskip']['editable'])
    def test_dependent_options_and_vectors_apply_in_backend_order(self):
        device=FakeDevice();p=c.profile_from_config({})
        p['sane_options']={'gamma-table':[0,20,180,255],'custom-gamma':True,'contrast':40}
        so.apply_profile(device,p)
        self.assertTrue(device.custom_gamma);self.assertEqual(device.gamma_table,[0,20,180,255])
        self.assertEqual(device.contrast,40)
    def test_auto_uses_native_duplex_source(self):
        device=FakeDevice()
        so.apply_profile(device,c.profile_from_config({}) | dict(source='Auto',blank_percent=0.1))
        self.assertEqual(device.source,'ADF Duplex')
    def test_a4_geometry_allows_native_submillimetre_rounding(self):
        device=QuantizedGeometryDevice()
        so.apply_profile(device,c.profile_from_config({}))
        for name,want in [('page_width',210),('page_height',297),('br_x',210),('br_y',297),('tl_x',0),('tl_y',0)]:
            self.assertAlmostEqual(getattr(device,name),want,delta=.011)
    def test_scan_area_follows_effective_rounded_page_extent(self):
        for source in ('ADF Front','ADF Duplex','Auto'):
            with self.subTest(source=source):
                device=DynamicGeometryDevice()
                profile=c.profile_from_config({}) | dict(source=source,blank_percent=0.1)
                so.apply_profile(device,profile)
                self.assertEqual(device.br_x,device.page_width)
                self.assertEqual(device.br_y,device.page_height)
                self.assertLess(device.page_height,297)
                self.assertAlmostEqual(device.page_height,297,delta=.011)
    def test_native_validation_error_identifies_the_setting(self):
        class NarrowDevice(QuantizedGeometryDevice):
            def get_options(self):
                return [(*row[:8],(0.,200.,0.)) if row[1]=='page-width' else row for row in super().get_options()]
        with self.assertRaisesRegex(ValueError,'page-width'):
            so.apply_profile(NarrowDevice(),c.profile_from_config({}))
    def test_geometry_bounds_and_integer_steps_stay_enforced(self):
        with self.assertRaises(ValueError):
            so.apply_profile(QuantizedGeometryDevice(),c.profile_from_config({}) | dict(width_mm=217))
        with self.assertRaises(ValueError):
            c.validate_value(3,dict(kind='integer',range=[0,10,2]))
    def test_inactive_or_invalid_vector_is_rejected(self):
        for values in ({'gamma-table':[0,20,180,255]}, {'custom-gamma':True,'gamma-table':[0,300,128,255]}, {'custom-gamma':True,'gamma-table':[0,128]}):
            with self.subTest(values=values),self.assertRaises(ValueError):
                so.apply_profile(FakeDevice(),c.profile_from_config({}) | {'sane_options':values})

if __name__=='__main__': unittest.main()
