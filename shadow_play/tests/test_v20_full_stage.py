import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import stage_v20_full_preparation as stage
import v20_full_preparation as model


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name);self.archive=self.path/'stage.tgz'
        self.built=stage.build(model.OUTPUT,self.archive)

    def modified_archive(self,mutate):
        with tarfile.open(self.archive,'r:gz') as tar:
            files={m.name:tar.extractfile(m).read() for m in tar}
        mutate(files)
        with tarfile.open(self.archive,'w:gz') as tar:
            for name,data in files.items():
                info=tarfile.TarInfo(name);info.size=len(data);tar.addfile(info,io.BytesIO(data))
        return stage.digest(self.archive.read_bytes())

    def test_installs_only_data_into_a_new_directory_and_rejects_overwrite(self):
        base=self.path/'sd';base.mkdir()
        result=stage.install(self.archive,self.built['sha256'],base)
        self.assertEqual(result['manifest_entries'],6)
        self.assertFalse(result['service_started']);self.assertFalse(result['motor_commands_sent'])
        self.assertEqual(set(p.name for p in Path(result['installed']).iterdir()),set((*stage.DATA_FILES,'MANIFEST.json')))
        before=(Path(result['installed'])/'score.json').read_bytes()
        with self.assertRaises(ValueError):stage.install(self.archive,self.built['sha256'],base)
        self.assertEqual((Path(result['installed'])/'score.json').read_bytes(),before)

    def test_archive_checksum_and_member_checksum_reject(self):
        with self.assertRaises(ValueError):stage.read_archive(self.archive,'0'*64)
        sha=self.modified_archive(lambda files:files.update({stage.RELEASE+'/readiness.json':b'{}'}))
        with self.assertRaises(ValueError):stage.read_archive(self.archive,sha)

    def test_traversal_extra_member_and_symlink_reject(self):
        for name in [stage.RELEASE+'/../outside',stage.RELEASE+'/runner.py','/tmp/outside']:
            self.built=stage.build(model.OUTPUT,self.archive)
            sha=self.modified_archive(lambda files:files.update({name:b'unsafe'}))
            with self.assertRaises(ValueError):stage.read_archive(self.archive,sha)
        with tarfile.open(self.archive,'w:gz') as tar:
            info=tarfile.TarInfo(stage.RELEASE+'/score.json');info.type=tarfile.SYMTYPE;info.linkname='/tmp/outside';tar.addfile(info)
        with self.assertRaises(ValueError):stage.read_archive(self.archive,stage.digest(self.archive.read_bytes()))

    def test_rehashed_execution_flags_still_reject(self):
        def mutate(files):
            name=stage.RELEASE+'/readiness.json';ready=json.loads(files[name]);ready['physical_performance_ready']=True
            files[name]=json.dumps(ready).encode()
            manifest=json.loads(files[stage.RELEASE+'/MANIFEST.json']);manifest['files']['readiness.json']=stage.digest(files[name])
            files[stage.RELEASE+'/MANIFEST.json']=json.dumps(manifest).encode()
        sha=self.modified_archive(mutate)
        with self.assertRaises(ValueError):stage.read_archive(self.archive,sha)

    def test_rehashed_reference_motor_command_rejects(self):
        def mutate(files):
            name=stage.RELEASE+'/reference_timeline.jsonl';rows=[json.loads(line) for line in files[name].splitlines()]
            rows[0]['motor_command']=[1500]*10
            files[name]=('\n'.join(json.dumps(row) for row in rows)+'\n').encode()
            manifest=json.loads(files[stage.RELEASE+'/MANIFEST.json']);manifest['files']['reference_timeline.jsonl']=stage.digest(files[name])
            files[stage.RELEASE+'/MANIFEST.json']=json.dumps(manifest).encode()
        sha=self.modified_archive(mutate)
        with self.assertRaises(ValueError):stage.read_archive(self.archive,sha)

    def test_output_verifier_rejects_corruption_and_flag_edits(self):
        folder=self.path/'copy';folder.mkdir()
        for name in (*model.OUTPUT_FILES,'MANIFEST.json'):shutil.copyfile(model.OUTPUT/name,folder/name)
        self.assertTrue(model.verify_output(folder)['software_integrity_passed'])
        ready=model.load(folder/'readiness.json');ready['physical_performance_ready']=True
        model.write_json(folder/'readiness.json',ready)
        with self.assertRaises(ValueError):model.verify_output(folder)
        manifest=model.load(folder/'MANIFEST.json');manifest['files']['readiness.json']=model.sha(folder/'readiness.json')
        model.write_json(folder/'MANIFEST.json',manifest)
        with self.assertRaises(ValueError):model.verify_output(folder)


if __name__=='__main__':unittest.main()
