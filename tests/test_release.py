# Modified for v1.0.0: normalized public identifiers and technical documentation.
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('wcmctl',ROOT/'tools/wcmctl.py')
wcm=importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcm)

class DistributionTests(unittest.TestCase):
    def test_device_metadata(self):
        for dev in wcm.DEVICES:
            self.assertEqual(wcm.device_info(dev)['id'],dev)
        self.assertFalse(wcm.device_info(wcm.FILM_ID)['deployable'])

    def test_virtual_install_boot_and_tamper(self):
        with tempfile.TemporaryDirectory(prefix='wcm-test-') as d:
            d=Path(d)
            bundle=d/'out'
            meta=wcm.build('virtual-node',bundle)
            self.assertFalse(meta['physical_hardware'])
            self.assertFalse(meta['hardware_qualified'])
            self.assertTrue(wcm.verify_bundle(bundle))
            image=d/'wcm-virtual.zip'
            wcm.zip_image(bundle,image)
            self.assertTrue(image.is_file())
            # The image itself contains the installer, not only the source tree.
            with tempfile.TemporaryDirectory(prefix='wcm-unpack-') as unpack:
                import zipfile, subprocess, sys
                with zipfile.ZipFile(image) as z: z.extractall(unpack)
                dest=d/'device'
                child=subprocess.run([sys.executable,str(Path(unpack)/'tools/wcmctl.py'),
                    'install','--bundle',str(Path(unpack)),'--device-root',str(dest)],
                    capture_output=True,text=True)
                self.assertEqual(child.returncode,0,child.stderr)
            status=wcm.boot(dest)
            self.assertEqual(status['reports_sent'],3)
            self.assertEqual(status['optical_symbols_emitted'],96)
            self.assertEqual(status['downlink_commands_received'],0)
            self.assertFalse(status['acknowledgements_expected'])
            self.assertFalse(status['receiver_algorithm_present'])
            exe=dest/'firmware/wcm_virtual_device'
            with exe.open('ab') as fp: fp.write(b'TAMPERED')
            with self.assertRaisesRegex(wcm.ReleaseError,'sha256 mismatch'):
                wcm.verify_bundle(dest)
            with self.assertRaisesRegex(wcm.ReleaseError,'sha256 mismatch'):
                wcm.boot(dest)

    def test_film_compile_rejected_install(self):
        with tempfile.TemporaryDirectory(prefix='wcm-test-') as d:
            d=Path(d)
            film=d/'film'
            meta=wcm.build('film-reference',film)
            self.assertEqual(meta['image_kind'],'verilog-rtl')
            self.assertIn('rtl/wcm_reference_core.v',meta['sha256'])
            with self.assertRaisesRegex(wcm.ReleaseError,'REFUSED'):
                wcm.install(film,d/'hardware')

    def test_reject_malicious_archive(self):
        import zipfile
        with tempfile.TemporaryDirectory(prefix='wcm-test-') as d:
            d=Path(d)
            with zipfile.ZipFile(d/'attack.zip','w') as z:
                z.writestr('../outside','escape')
            with self.assertRaises(wcm.ReleaseError):
                wcm.install(d/'attack.zip',d/'device')
            self.assertFalse((d/'outside').exists())

    def test_reject_unsafe_manifest_path(self):
        with tempfile.TemporaryDirectory(prefix='wcm-test-') as d:
            d=Path(d); bundle=wcm.build('virtual-node',d/'safe')
            m=bundle.copy();m['artifacts'][0]='../outside';m['sha256']['../outside']=m['sha256'].pop('device.toml')
            (d/'safe/manifest.json').write_text(json.dumps(m))
            with self.assertRaises(wcm.ReleaseError):wcm.verify_bundle(d/'safe')

if __name__=='__main__':unittest.main()
