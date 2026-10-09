"""Windows/desktop STS2 remote jobs over verified OpenSSH transport."""

from dataclasses import dataclass, asdict
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import uuid

from megcfbt.sts2_backend import module
from megcfbt.sts2 import tools_directory


class RemoteError(RuntimeError): pass


def settings_directory():
    return Path(os.environ.get('APPDATA', Path.home()/'.config'))/'megcfbt/sts2'


@dataclass
class FrameSettings:
    host: str = 'frame'
    user: str = 'steamos'
    port: int = 22
    key_file: str = ''
    remote_root: str = '/run/media/steamos/SD512/megcfbt-sts2'
    sdk_file: str = ''
    remote_sdk: str = ''
    download_archive: bool = True

    def validate(self):
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.:-]*',self.host): raise RemoteError('Enter a Frame hostname or IP address.')
        if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_-]*',self.user): raise RemoteError('Invalid Frame user name.')
        if not 1<=int(self.port)<=65535: raise RemoteError('Invalid connection port.')
        if not re.fullmatch(r'[A-Za-z0-9_./ -]+',self.remote_root):
            raise RemoteError('Frame destination contains unsupported shell characters.')
        path=PurePosixPath(self.remote_root)
        if not path.is_absolute() or '..' in path.parts or '\\' in self.remote_root: raise RemoteError('Invalid Frame destination.')
        if not (self.remote_root.startswith('/run/media/'+self.user+'/') or self.remote_root.startswith('/home/'+self.user+'/')):
            raise RemoteError('Choose writable user storage; system directories are not permitted.')
        if any(p in path.parts for p in ('steamapps','userdata','SlayTheSpire2','.ssh','.steam')):
            raise RemoteError('Use a separate application directory, outside game installations and saves.')
        if self.key_file and not Path(self.key_file).is_file(): raise RemoteError('The selected connection key file is missing.')

    def save(self):
        self.validate(); root=settings_directory();root.mkdir(parents=True,exist_ok=True)
        target=root/'connection.json';temporary=root/'connection.json.part'
        temporary.write_text(json.dumps(asdict(self),indent=2)+'\n')
        os.replace(temporary,target)

    @classmethod
    def load(cls):
        try:
            data=json.loads((settings_directory()/'connection.json').read_bytes())
            return cls(**{k:v for k,v in data.items() if k in cls.__dataclass_fields__})
        except (OSError,ValueError,TypeError): return cls()


def ssh_program():
    result=shutil.which('ssh')
    if not result and os.name=='nt':
        path=Path(os.environ.get('WINDIR','C:/Windows'))/'System32/OpenSSH/ssh.exe'
        if path.is_file(): result=str(path)
    if not result: raise RemoteError('Windows OpenSSH Client is required. Enable it in Windows Optional Features, then reopen the application.')
    return result


def process_options():
    return {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}


class FrameTransport:
    def __init__(self,settings): self.settings=settings;settings.validate()

    def arguments(self,command):
        s=self.settings
        args=[ssh_program(),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
              '-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-p',str(s.port)]
        trust=settings_directory()/'known_hosts'
        if trust.exists():
            default=Path.home()/'.ssh/known_hosts'
            names=' '.join('"'+p.as_posix()+'"' for p in (trust,default))
            args += ['-o','UserKnownHostsFile='+names]
        if s.key_file: args += ['-i',s.key_file,'-o','IdentitiesOnly=yes']
        return args+[s.user+'@'+s.host,command]

    def run(self,command,*,data=None,timeout=60):
        result=subprocess.run(self.arguments(command),input=data,capture_output=True,timeout=timeout,**process_options())
        if result.returncode:
            error=result.stderr.decode('utf-8',errors='replace')[-4000:]
            try:
                report=json.loads(result.stdout.decode('utf-8'))
                if report.get('type')=='error': error=report['message']
            except (ValueError,AttributeError,KeyError): pass
            raise RemoteError('Secure Frame connection failed: '+error)
        return result.stdout

    def host_fingerprint(self):
        scan=shutil.which('ssh-keyscan') or str(Path(ssh_program()).with_name('ssh-keyscan.exe' if os.name=='nt' else 'ssh-keyscan'))
        result=subprocess.run([scan,'-T','10','-p',str(self.settings.port),'-t','ed25519',self.settings.host],capture_output=True,timeout=20,**process_options())
        lines=[l for l in result.stdout.decode().splitlines() if l and not l.startswith('#')]
        if len(lines)!=1: raise RemoteError('Unable to read a unique Frame host identity.')
        fields=lines[0].split()
        fingerprint='SHA256:'+base64.b64encode(hashlib.sha256(base64.b64decode(fields[2])).digest()).decode().rstrip('=')
        return fingerprint,lines[0]

    def trust_new_host(self,line):
        # A changed existing key must not be repaired silently through this UI.
        keygen=shutil.which('ssh-keygen') or str(Path(ssh_program()).with_name('ssh-keygen.exe' if os.name=='nt' else 'ssh-keygen'))
        host=self.settings.host if self.settings.port==22 else f'[{self.settings.host}]:{self.settings.port}'
        for known in (Path.home()/'.ssh/known_hosts',settings_directory()/'known_hosts'):
            if known.exists():
                result=subprocess.run([keygen,'-F',host,'-f',str(known)],capture_output=True,**process_options())
                if result.returncode==0 and result.stdout.strip():
                    raise RemoteError('This host already has a trusted identity. A changed key needs independent verification; it will not be replaced automatically.')
        root=settings_directory();root.mkdir(parents=True,exist_ok=True)
        with (root/'known_hosts').open('a',encoding='utf-8') as stream: stream.write(line+'\n')


# Bootstrap is application source, sent via a quoted command; binary tar is stdin.
BOOTSTRAP = r'''
import sys,json,os,hashlib,tarfile,io
from pathlib import Path,PurePosixPath
base=Path(sys.argv[1]); identity=sys.argv[2]; digest=sys.argv[3]; length=int(sys.argv[4])
if not base.is_absolute() or '..' in base.parts or any(p.is_symlink() for p in (base,*base.parents)): raise SystemExit('Unsafe workspace root')
if length>16*1024*1024: raise SystemExit('Software bundle exceeds limit')
raw=sys.stdin.buffer.read(length+1)
if len(raw)!=length or hashlib.sha256(raw).hexdigest()!=digest: raise SystemExit('Software bundle checksum mismatch')
root=base/'jobs'/('job-'+identity)
root.mkdir(parents=True,mode=0o700)
(root/'job.json').write_text(json.dumps({'kind':'megcfbt-sts2-job-v1','id':identity}))
tools=root/'backend'; tools.mkdir()
with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
 seen=set()
 for member in archive:
  p=PurePosixPath(member.name)
  if not member.isfile() or p.is_absolute() or '..' in p.parts or '\\' in member.name or ':' in member.name or p.as_posix()!=member.name or member.name in seen: raise SystemExit('Unsafe software member')
  seen.add(member.name);target=tools.joinpath(*p.parts);target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as output: output.write(archive.extractfile(member).read())
print(json.dumps({'job':str(root)}))
'''


def backend_bundle(destination):
    directory=tools_directory();package=module('package_converter')
    with tarfile.open(destination,'w') as archive:
        for name in package.FILES:
            archive.add(directory/name,arcname=name,recursive=False)
        license=directory/'LICENSE'
        if not license.exists(): license=directory.parents[1]/'LICENSE'
        archive.add(license,arcname='LICENSE',recursive=False)


def digest_file(path,limit=None):
    digest=hashlib.sha256();remaining=limit
    with Path(path).open('rb') as stream:
        while remaining is None or remaining>0:
            block=stream.read(min(1024*1024,remaining) if remaining is not None else 1024*1024)
            if not block: break
            digest.update(block)
            if remaining is not None: remaining-=len(block)
    return digest.hexdigest()


class RemoteBuild:
    def __init__(self,settings,progress=None,stage=None):
        self.settings=settings;self.transport=FrameTransport(settings)
        self.progress=progress or (lambda m:None);self.stage=stage or (lambda v,m:None)

    def worker(self,job,action,extra=()):
        return shlex.join(['python3',job+'/backend/remote_worker.py',action,job,*map(str,extra)])

    def probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle=Path(temporary)/'backend.tar';backend_bundle(bundle)
            raw=bundle.read_bytes(); identity=uuid.uuid4().hex
            command=shlex.join(['python3','-c',BOOTSTRAP,self.settings.remote_root,identity,hashlib.sha256(raw).hexdigest(),str(len(raw))])
            job=json.loads(self.transport.run(command,data=raw))['job']
            report=json.loads(self.transport.run(shlex.join(['python3',job+'/backend/remote_worker.py','probe',self.settings.remote_root])))
            report['probe_job']=job
        problems=[]
        if report['architecture'] not in ('aarch64','arm64'): problems.append('Frame must run Linux AArch64.')
        if report['free_bytes']<10*1024**3: problems.append('At least 10 GiB free build storage is required.')
        if not report['writable']: problems.append('The selected destination is not writable.')
        if not all(report['tools'].values()): problems.append('Frame compiler tools are missing: '+', '.join(k for k,v in report['tools'].items() if not v))
        if not report['valve_api_verified'] or not report['valve_host_runtime']: problems.append('The supported Valve ARM64 runtimes are missing or changed.')
        if problems: raise RemoteError(' '.join(problems))
        return report

    def steam_entry(self,job,action,*,consent=False,isolated=False):
        if action not in {'inspect','configure','restore'}:
            raise RemoteError('Unknown Steam integration action')
        if not job.startswith(self.settings.remote_root+'/jobs/job-'):
            raise RemoteError('Steam output is outside the configured application workspace')
        # Use current application software even when configuring an older retained output.
        probe=self.probe()
        extra=['--name',job]
        if consent: extra.append('--consent')
        if isolated: extra.append('--isolated')
        report=json.loads(self.transport.run(self.worker(probe['probe_job'],'steam-'+action,extra)))
        if report.get('event')=='error' or report.get('type')=='error':
            raise RemoteError(report.get('message','Steam configuration failed'))
        return report

    def upload(self,job,path,name,value):
        size=Path(path).stat().st_size;digest=digest_file(path)
        status=json.loads(self.transport.run(self.worker(job,'status',['--name',name])))
        if status['complete']:
            if status['complete']['sha256']!=digest or status['complete']['size']!=size: raise RemoteError('Existing job input differs; choose a new job.')
            return
        offset=status['offset']
        if offset>size or digest_file(path,offset)!=status['prefix_sha256']: raise RemoteError('Partial transfer differs from local input; choose a new job.')
        command=self.worker(job,'upload',['--name',name,'--size',size,'--sha256',digest,'--offset',offset])
        with tempfile.TemporaryFile() as error:
            process=subprocess.Popen(self.transport.arguments(command),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=error,**process_options())
            try:
                with Path(path).open('rb') as source:
                    source.seek(offset)
                    while block:=source.read(1024*1024):
                        process.stdin.write(block);offset+=len(block)
                        if offset==size or offset % (16*1024*1024)==0:
                            self.stage(value,minimal_transfer(name,offset,size))
                process.stdin.close()
                payload=process.stdout.read();code=process.wait()
            except BaseException:
                process.terminate();process.wait();raise
            if code:
                error.seek(0);raise RemoteError('Transfer interrupted; retry can resume this job. '+error.read().decode(errors='replace')[-2000:])
            report=json.loads(payload)
            if not report.get('verified'): raise RemoteError(report.get('message','Upload verification failed'))

    def build(self,source,local_output,archive=True,resume_job=None):
        s=self.settings
        self.stage(.03,'Checking source files')
        report=module('preflight').inspect_source(source)
        if report['errors']: raise RemoteError('Unsupported or altered source: '+str(report['errors']))
        self.stage(.07,'Checking Frame and build requirements')
        preflight=self.probe()
        sdk=s.remote_sdk or (preflight['sdk_candidates'][0] if preflight['sdk_candidates'] and not s.sdk_file else '')
        if not sdk and not s.sdk_file: raise RemoteError('Select the FMOD 2.03.15 Linux SDK archive in Frame setup.')
        if s.sdk_file:
            pin=module('sdk_archive').PIN
            with module('converter_io').verified_stream(Path(s.sdk_file),pin): pass
        local_output=Path(local_output)
        local_output.mkdir(parents=True,exist_ok=True)
        identity=uuid.uuid4().hex
        job=resume_job or preflight['probe_job']
        receipt_path=local_output/('sts2-job-'+Path(job).name+'.json')
        profile=module('convert_sts2').load_profile(source)
        identity=hashlib.sha256(json.dumps(profile,sort_keys=True).encode()).hexdigest()
        receipt={'job':job,'host':s.host,'status':'building','source_profile_sha256':identity}
        if resume_job:
            if not job.startswith(s.remote_root+'/jobs/job-'): raise RemoteError('Retry job is outside the configured application workspace.')
            previous=json.loads(receipt_path.read_bytes())
            if previous.get('host')!=s.host or previous.get('source_profile_sha256')!=identity: raise RemoteError('Retry source/host differs from the previous job.')
        receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
        with tempfile.TemporaryDirectory(prefix='sts2-input-',dir=local_output) as temporary:
            package=Path(temporary)/'source.tar'
            profile=module('convert_sts2').load_profile(source)
            records={p['source']:p for p in profile['copy_files']}
            records.update({'data_sts2_windows_x86_64/'+n:p for n,p in profile['managed_inputs'].items()})
            records['SlayTheSpire2.pck']=profile['pack']
            self.stage(.12,'Preparing verified source transfer')
            with tarfile.open(package,'w') as output:
                for name,pin in records.items():
                    with module('converter_io').verified_stream(Path(source)/module('converter_io').relative(name),pin) as stream:
                        item=tarfile.TarInfo(name);item.size=pin['size_bytes'];item.mode=0o644
                        output.addfile(item,stream)
            self.stage(.20,'Checking previously verified original-input transfers')
            self.transport.run(self.worker(job,'reuse-input',['--name','source.tar','--size',package.stat().st_size,'--sha256',digest_file(package)]))
            self.upload(job,package,'source.tar',.22)
            if s.sdk_file: self.upload(job,Path(s.sdk_file),'sdk.tar.gz',.32)
        args=['--sdk',sdk] if sdk else []
        if archive and s.download_archive: args+=['--archive']
        self.stage(.40,'Building on Frame')
        with tempfile.TemporaryFile() as errors:
            process=subprocess.Popen(self.transport.arguments(self.worker(job,'build',args)),stdout=subprocess.PIPE,stderr=errors,text=True,**process_options())
            result=None;last_error=''
            for line in process.stdout:
                event=json.loads(line)
                if event['type']=='progress': self.stage(event['value'],event['message']);self.progress(event['message'])
                elif event['type']=='result': result=event
                elif event['type']=='error': last_error=event['message'];self.progress(event['message'])
            code=process.wait()
            if code or result is None:
                errors.seek(0);detail=errors.read().decode(errors='replace')[-4000:]
                receipt.update(status='failed',detail=last_error+'\n'+detail)
                receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
                raise RemoteError('Frame build failed: '+last_error+'\nPrivate job retained for retry: '+job+'\n'+detail)
        archive_path=None
        if result.get('archive'):
            self.stage(.94,'Downloading verified transfer archive')
            archive_path=local_output/('STS2-'+Path(job).name+'.tar')
            partial=archive_path.with_suffix('.tar.part')
            remote_path=result['archive']
            expected=json.loads(self.transport.run(shlex.join(['python3','-c',"import hashlib,json,sys;from pathlib import Path;p=Path(sys.argv[1]);print(json.dumps({'sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest(),'size':p.stat().st_size}))",remote_path])))
            with partial.open('xb') as output:
                process=subprocess.Popen(self.transport.arguments('cat -- '+shlex.quote(remote_path)),stdout=output,stderr=subprocess.PIPE,**process_options())
                _,error=process.communicate()
                if process.returncode: raise RemoteError('Archive download interrupted: '+error.decode(errors='replace'))
            if partial.stat().st_size!=expected['size'] or digest_file(partial)!=expected['sha256']: raise RemoteError('Downloaded archive checksum mismatch')
            os.rename(partial,archive_path)
        result.update(local_archive=str(archive_path) if archive_path else None,job=job,status='complete',source_profile_sha256=identity,host=s.host)
        receipt_path.write_text(json.dumps(result,indent=2)+'\n')
        self.stage(1.,'Verified native game deployed on Frame')
        return result

    def last_retry_job(self,local_output,source):
        profile=module('convert_sts2').load_profile(source)
        identity=hashlib.sha256(json.dumps(profile,sort_keys=True).encode()).hexdigest()
        for path in sorted(Path(local_output).glob('sts2-job-*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
            record=json.loads(path.read_bytes())
            if record.get('host')==self.settings.host and record.get('source_profile_sha256')==identity and record.get('status') in ('failed','building'):
                return record['job']
        raise RemoteError('No matching interrupted job exists. Start a new conversion.')


def minimal_transfer(name,offset,total):
    return f'Transferring {"game files" if name=="source.tar" else "FMOD SDK"}: {offset//1048576} / {total//1048576} MiB'
