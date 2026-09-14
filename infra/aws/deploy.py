"""AWS deployment commands. Secrets stay in AWS or in process memory.

Run with Python 3.12+, boto3 and an authenticated AWS CLI v2 session.
Local state and build artifacts live under the git-ignored data/salida directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
import secrets
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/salida/aws_deploy_20260914'
OUT.mkdir(parents=True, exist_ok=True)
STACK = 'aquanqa-production'
REGION = 'us-east-1'
ACCOUNT = '021686096399'


def session():
    p = subprocess.run(['aws', 'configure', 'export-credentials', '--format', 'process'],
                       capture_output=True, text=True, check=True)
    c = json.loads(p.stdout)
    s = boto3.Session(aws_access_key_id=c['AccessKeyId'],
                      aws_secret_access_key=c['SecretAccessKey'],
                      aws_session_token=c.get('SessionToken'), region_name=REGION)
    if s.client('sts').get_caller_identity()['Account'] != ACCOUNT:
        raise RuntimeError('Unexpected AWS account')
    return s


def save(name, value):
    (OUT / (name + '.json')).write_text(json.dumps(value, indent=2, default=str), encoding='utf-8')


def load(name):
    return json.loads((OUT / (name + '.json')).read_text(encoding='utf-8'))


def outputs(s):
    stack = s.client('cloudformation').describe_stacks(StackName=STACK)['Stacks'][0]
    return {x['OutputKey']: x['OutputValue'] for x in stack.get('Outputs', [])}


def base_template():
    ref = lambda x: {'Ref': x}
    att = lambda x, y: {'Fn::GetAtt': [x, y]}
    sub = lambda x: {'Fn::Sub': x}
    resources = {}
    def add(name, kind, props, **kw):
        resources[name] = {'Type': 'AWS::' + kind, 'Properties': props, **kw}
    tags = [{'Key': 'Project', 'Value': 'aquanqa'}, {'Key': 'Environment', 'Value': 'production'}]
    vpc = 'vpc-064a8e11f19905e9a'
    subnets = ['subnet-0a3eab02d96435283', 'subnet-0758e90d9474305bf']
    for name in ['ApiSecurityGroup', 'DbSecurityGroup', 'AlbSecurityGroup']:
        add(name, 'EC2::SecurityGroup', {'GroupDescription': 'Aquanqa ' + name, 'VpcId': vpc, 'Tags': tags})
    add('ApiIngress', 'EC2::SecurityGroupIngress', {'GroupId': ref('ApiSecurityGroup'), 'IpProtocol': 'tcp', 'FromPort': 8000, 'ToPort': 8000, 'SourceSecurityGroupId': ref('AlbSecurityGroup')})
    add('DbIngress', 'EC2::SecurityGroupIngress', {'GroupId': ref('DbSecurityGroup'), 'IpProtocol': 'tcp', 'FromPort': 5432, 'ToPort': 5432, 'SourceSecurityGroupId': ref('ApiSecurityGroup')})
    add('AlbVpcIngress', 'EC2::SecurityGroupIngress', {'GroupId': ref('AlbSecurityGroup'), 'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80, 'CidrIp': '172.31.0.0/16'})
    add('DbSubnetGroup', 'RDS::DBSubnetGroup', {'DBSubnetGroupDescription': 'Aquanqa private database', 'SubnetIds': subnets, 'Tags': tags})
    add('Database', 'RDS::DBInstance', {
        'DBInstanceIdentifier': 'aquanqa-production', 'DBName': 'aquanqa', 'Engine': 'postgres', 'EngineVersion': '18.3',
        'DBInstanceClass': 'db.t4g.micro', 'AllocatedStorage': '20', 'MaxAllocatedStorage': 100,
        'StorageType': 'gp3', 'StorageEncrypted': True, 'MasterUsername': 'aquanqa_owner', 'ManageMasterUserPassword': True,
        'DBSubnetGroupName': ref('DbSubnetGroup'), 'VPCSecurityGroups': [ref('DbSecurityGroup')],
        'PubliclyAccessible': False, 'MultiAZ': False, 'BackupRetentionPeriod': 1,
        'PreferredBackupWindow': '07:00-08:00', 'PreferredMaintenanceWindow': 'sun:08:00-sun:09:00',
        'AutoMinorVersionUpgrade': True, 'DeletionProtection': True, 'CopyTagsToSnapshot': True,
        'EnableCloudwatchLogsExports': ['postgresql', 'upgrade'], 'Tags': tags,
    }, DeletionPolicy='Snapshot', UpdateReplacePolicy='Snapshot')
    for name, suffix in [('Assets', 'assets'), ('Artifacts', 'artifacts')]:
        add(name, 'S3::Bucket', {
            'BucketName': f'aquanqa-{ACCOUNT}-{REGION}-{suffix}',
            'PublicAccessBlockConfiguration': {k: True for k in ['BlockPublicAcls','IgnorePublicAcls','BlockPublicPolicy','RestrictPublicBuckets']},
            'BucketEncryption': {'ServerSideEncryptionConfiguration': [{'ServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]},
            'VersioningConfiguration': {'Status': 'Enabled'}, 'Tags': tags,
        }, DeletionPolicy='Retain', UpdateReplacePolicy='Retain')
        add(name + 'Policy', 'S3::BucketPolicy', {'Bucket': ref(name), 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [{'Effect': 'Deny', 'Principal': '*', 'Action': 's3:*', 'Resource': [att(name, 'Arn'), sub('${' + name + '.Arn}/*')], 'Condition': {'Bool': {'aws:SecureTransport': 'false'}}}]}})
    for name in ['ApiRepository', 'MigrationRepository']:
        add(name, 'ECR::Repository', {'RepositoryName': 'aquanqa/' + ('api' if name == 'ApiRepository' else 'migration'), 'ImageTagMutability': 'IMMUTABLE', 'ImageScanningConfiguration': {'ScanOnPush': True}, 'EncryptionConfiguration': {'EncryptionType': 'AES256'}, 'Tags': tags}, DeletionPolicy='Retain', UpdateReplacePolicy='Retain')
    add('Cluster', 'ECS::Cluster', {'ClusterName': STACK, 'ClusterSettings': [{'Name': 'containerInsights', 'Value': 'enabled'}], 'Tags': tags})
    for name, suffix in [('ApiLogs', 'api'), ('MigrationLogs', 'migration'), ('BuildLogs', 'build')]:
        add(name, 'Logs::LogGroup', {'LogGroupName': '/aquanqa/production/' + suffix, 'RetentionInDays': 30, 'Tags': tags})
    def role(name, service, statements, managed=None):
        p = {'AssumeRolePolicyDocument': {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Principal': {'Service': service}, 'Action': 'sts:AssumeRole'}]}, 'Policies': [{'PolicyName': 'aquanqa', 'PolicyDocument': {'Version': '2012-10-17', 'Statement': statements}}], 'Tags': tags}
        if managed: p['ManagedPolicyArns'] = managed
        add(name, 'IAM::Role', p)
    secret_resources = [sub('arn:aws:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:aquanqa/production/*'), att('Database', 'MasterUserSecret.SecretArn')]
    role('ExecutionRole', 'ecs-tasks.amazonaws.com', [{'Effect':'Allow','Action':['secretsmanager:GetSecretValue'],'Resource':secret_resources}], ['arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy'])
    role('MigrationRole', 'ecs-tasks.amazonaws.com', [
        {'Effect':'Allow','Action':['secretsmanager:GetSecretValue'],'Resource':secret_resources},
        {'Effect':'Allow','Action':['s3:GetObject','s3:PutObject'],'Resource':sub('${Artifacts.Arn}/migration/*')},
    ])
    role('BuildRole', 'codebuild.amazonaws.com', [
        {'Effect':'Allow','Action':['logs:CreateLogStream','logs:PutLogEvents'],'Resource':sub('${BuildLogs.Arn}:*')},
        {'Effect':'Allow','Action':['s3:GetObject','s3:GetObjectVersion'],'Resource':sub('${Artifacts.Arn}/build/*')},
        {'Effect':'Allow','Action':['ecr:GetAuthorizationToken'],'Resource':'*'},
        {'Effect':'Allow','Action':['ecr:BatchCheckLayerAvailability','ecr:InitiateLayerUpload','ecr:UploadLayerPart','ecr:CompleteLayerUpload','ecr:PutImage','ecr:BatchGetImage','ecr:GetDownloadUrlForLayer'],'Resource':[att('ApiRepository','Arn'),att('MigrationRepository','Arn')]},
    ])
    add('Build', 'CodeBuild::Project', {
        'Name': STACK, 'ServiceRole': att('BuildRole','Arn'), 'Artifacts': {'Type':'NO_ARTIFACTS'},
        'Source': {'Type':'S3','Location':sub('${Artifacts}/build/source.zip'),'BuildSpec':'infra/aws/buildspec.yml'},
        'Environment': {'Type':'LINUX_CONTAINER','ComputeType':'BUILD_GENERAL1_SMALL','Image':'aws/codebuild/standard:7.0','PrivilegedMode':True},
        'TimeoutInMinutes':30, 'LogsConfig': {'CloudWatchLogs': {'Status':'ENABLED','GroupName':ref('BuildLogs')}}, 'Tags':tags,
    })
    add('LoadBalancer','ElasticLoadBalancingV2::LoadBalancer',{'Name':STACK,'Scheme':'internal','Type':'application','Subnets':subnets,'SecurityGroups':[ref('AlbSecurityGroup')],'LoadBalancerAttributes':[{'Key':'routing.http.drop_invalid_header_fields.enabled','Value':'true'}],'Tags':tags})
    add('TargetGroup','ElasticLoadBalancingV2::TargetGroup',{'Name':'aquanqa-api','VpcId':vpc,'Port':8000,'Protocol':'HTTP','TargetType':'ip','HealthCheckPath':'/v1/health/ready','HealthCheckIntervalSeconds':30,'HealthyThresholdCount':2,'UnhealthyThresholdCount':3,'TargetGroupAttributes':[{'Key':'deregistration_delay.timeout_seconds','Value':'30'}],'Tags':tags})
    add('Listener','ElasticLoadBalancingV2::Listener',{'LoadBalancerArn':ref('LoadBalancer'),'Port':80,'Protocol':'HTTP','DefaultActions':[{'Type':'forward','TargetGroupArn':ref('TargetGroup')}]})
    out = {n: {'Value': ref(n)} for n in ['Assets','Artifacts','Cluster','ApiSecurityGroup','DbSecurityGroup','AlbSecurityGroup','TargetGroup','LoadBalancer']}
    out.update({n:{'Value':att(n,'Arn')} for n in ['ExecutionRole','MigrationRole']})
    out.update({'DbHost':{'Value':att('Database','Endpoint.Address')},'DbSecret':{'Value':att('Database','MasterUserSecret.SecretArn')},'AlbHost':{'Value':att('LoadBalancer','DNSName')}})
    return {'AWSTemplateFormatVersion':'2010-09-09','Description':'Aquanqa API, private PostgreSQL, build and static hosting foundations','Resources':resources,'Outputs':out}


def base(s):
    t = base_template()
    (ROOT/'infra/aws/production.json').write_text(json.dumps(t, indent=2), encoding='utf-8')
    cf = s.client('cloudformation')
    cf.validate_template(TemplateBody=json.dumps(t))
    result = cf.create_stack(StackName=STACK, TemplateBody=json.dumps(t), Capabilities=['CAPABILITY_IAM'],
                             DisableRollback=True, Tags=[{'Key':'Project','Value':'aquanqa'}])
    save('stack',result)
    print('Infrastructure stack creation started')


def status(s):
    cf = s.client('cloudformation')
    d = cf.describe_stacks(StackName=STACK)['Stacks'][0]
    print('stack:',d['StackStatus'])
    for e in cf.describe_stack_events(StackName=STACK)['StackEvents'][:12]:
        print(e['LogicalResourceId'],e['ResourceStatus'],e.get('ResourceStatusReason',''))
    if d.get('Outputs'): save('outputs', outputs(s))


def retry(s):
    t = base_template()
    (ROOT/'infra/aws/production.json').write_text(json.dumps(t, indent=2), encoding='utf-8')
    s.client('cloudformation').update_stack(StackName=STACK, TemplateBody=json.dumps(t),
        Capabilities=['CAPABILITY_IAM'], DisableRollback=True)
    print('Infrastructure update started')


def build(s):
    source = OUT/'source.zip'
    roots = [ROOT/'backend/campo-api', ROOT/'infra/aws']
    files = []
    for root in roots:
        for path in root.rglob('*'):
            if not path.is_file(): continue
            if any(x in {'__pycache__','.pytest_cache','.ruff_cache','.venv','build','dist','tests'} or x.endswith('.egg-info') for x in path.relative_to(root).parts): continue
            if path.suffix in {'.pyc','.log'} or path.name.startswith('.env'): continue
            files.append(path)
    with zipfile.ZipFile(source,'w',zipfile.ZIP_DEFLATED) as z:
        for path in sorted(files): z.write(path,path.relative_to(ROOT).as_posix())
    release = 'r'+hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    bucket = f'aquanqa-{ACCOUNT}-{REGION}-artifacts'
    key = 'build/'+release+'.zip'
    s.client('s3').upload_file(str(source),bucket,key)
    result = s.client('codebuild').start_build(projectName=STACK,
        sourceLocationOverride=bucket+'/'+key,
        environmentVariablesOverride=[{'name':'REGISTRY','value':f'{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com','type':'PLAINTEXT'},{'name':'RELEASE','value':release,'type':'PLAINTEXT'}])
    save('build',{'id':result['build']['id'],'release':release})
    print('Build started:',result['build']['id'],'release:',release)


def build_status(s):
    d=s.client('codebuild').batch_get_builds(ids=[load('build')['id']])['builds'][0]
    print(d['buildStatus'],d.get('currentPhase'))
    for p in d.get('phases',[]):
        if p.get('contexts'): print(p['phaseType'],p['contexts'])
    logs=d.get('logs',{})
    if logs.get('streamName'):
        for e in s.client('logs').get_log_events(logGroupName=logs['groupName'],logStreamName=logs['streamName'],limit=14)['events']: print(e['message'].rstrip())


def setup(s):
    from backup import render_config
    o=outputs(s)
    _,_,env=render_config()
    sm=s.client('secretsmanager')
    name='aquanqa/production/api'
    try:
        d=sm.get_secret_value(SecretId=name)
        app=json.loads(d['SecretString'])
        arn=d['ARN']
    except sm.exceptions.ResourceNotFoundException:
        password=secrets.token_hex(32)
        app={'password':password,'jwt':env['AQUANQA_JWT_SECRET'],
             'rehearsal_url':f"postgresql://aquanqa_app:{password}@{o['DbHost']}:5432/aquanqa?sslmode=require",
             'production_url':f"postgresql://aquanqa_app:{password}@{o['DbHost']}:5432/aquanqa_live?sslmode=require"}
        arn=sm.create_secret(Name=name,SecretString=json.dumps(app),Tags=[{'Key':'Project','Value':'aquanqa'}])['ARN']
    save('app-secret',{'arn':arn})
    print('Runtime secret configured; JWT continuity preserved')


def network(o):
    return {'awsvpcConfiguration':{'subnets':['subnet-0a3eab02d96435283','subnet-0758e90d9474305bf'],'securityGroups':[o['ApiSecurityGroup']],'assignPublicIp':'ENABLED'}}


def restore(s):
    o=outputs(s);release=load('build')['release']; ecs=s.client('ecs')
    backup_name=os_environ('BACKUP','rehearsal-01')
    db=os_environ('DB_NAME','aquanqa')
    env={'DB_HOST':o['DbHost'],'DB_SECRET':o['DbSecret'],'APP_SECRET':load('app-secret')['arn'],'BUCKET':o['Artifacts'],'BACKUP':backup_name,'DB_NAME':db,'AWS_DEFAULT_REGION':REGION}
    task=ecs.register_task_definition(family='aquanqa-migration',networkMode='awsvpc',requiresCompatibilities=['FARGATE'],cpu='1024',memory='2048',executionRoleArn=o['ExecutionRole'],taskRoleArn=o['MigrationRole'],containerDefinitions=[{
        'name':'migration','image':f'{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/aquanqa/migration:{release}','essential':True,
        'environment':[{'name':k,'value':v} for k,v in env.items()],
        'logConfiguration':{'logDriver':'awslogs','options':{'awslogs-group':'/aquanqa/production/migration','awslogs-region':REGION,'awslogs-stream-prefix':'migration'}},
    }])['taskDefinition']['taskDefinitionArn']
    d=ecs.run_task(cluster=o['Cluster'],taskDefinition=task,launchType='FARGATE',networkConfiguration=network(o),count=1)
    if d.get('failures'): raise RuntimeError(d['failures'])
    save('restore-task',{'arn':d['tasks'][0]['taskArn'],'backup':backup_name,'db':db})
    print('Restore task started:',d['tasks'][0]['taskArn'])


def os_environ(key,default):
    import os
    return os.environ.get(key,default)


def restore_status(s):
    o=outputs(s);task=load('restore-task')['arn']
    d=s.client('ecs').describe_tasks(cluster=o['Cluster'],tasks=[task])['tasks'][0]
    print(d['lastStatus'],d.get('stoppedReason',''),[{k:v for k,v in c.items() if k in ['name','exitCode','reason','lastStatus']} for c in d['containers']])
    try:
        for e in s.client('logs').get_log_events(logGroupName='/aquanqa/production/migration',logStreamName='migration/migration/'+task.split('/')[-1],limit=20)['events']: print(e['message'])
    except s.client('logs').exceptions.ResourceNotFoundException: pass


def api(s):
    o=outputs(s); ecs=s.client('ecs');release=load('build')['release']
    live=os_environ('DB_NAME','aquanqa')=='aquanqa_live'
    db='aquanqa_live' if live else 'aquanqa'
    secret=load('app-secret')['arn']
    env={'AQUANQA_API_DATABASE':db,'AQUANQA_API_ENVIRONMENT':'production','AQUANQA_API_DATABASE_POOL_MIN_SIZE':'2','AQUANQA_API_DATABASE_POOL_MAX_SIZE':'8','AQUANQA_API_DATABASE_POOL_TIMEOUT_SECONDS':'15'}
    if (OUT/'distribution.json').exists(): env['AQUANQA_API_PUBLIC_URL']='https://'+load('distribution')['domain']
    task=ecs.register_task_definition(family='aquanqa-api',networkMode='awsvpc',requiresCompatibilities=['FARGATE'],cpu='512',memory='1024',executionRoleArn=o['ExecutionRole'],containerDefinitions=[{
        'name':'api','image':f'{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/aquanqa/api:{release}','essential':True,
        'portMappings':[{'containerPort':8000,'protocol':'tcp'}],
        'environment':[{'name':k,'value':v} for k,v in env.items()],
        'secrets':[{'name':'AQUANQA_API_DATABASE_URL','valueFrom':secret+(':'+('production_url' if live else 'rehearsal_url')+'::')},{'name':'AQUANQA_JWT_SECRET','valueFrom':secret+':jwt::'}],
        'healthCheck':{'command':['CMD','python','-c',"import urllib.request; urllib.request.urlopen('http://localhost:8000/v1/health/live')"],'interval':30,'timeout':5,'retries':3,'startPeriod':60},
        'logConfiguration':{'logDriver':'awslogs','options':{'awslogs-group':'/aquanqa/production/api','awslogs-region':REGION,'awslogs-stream-prefix':'api'}},
    }])['taskDefinition']['taskDefinitionArn']
    existing=ecs.describe_services(cluster=o['Cluster'],services=['aquanqa-api'])['services']
    config={'deploymentCircuitBreaker':{'enable':True,'rollback':True},'maximumPercent':200,'minimumHealthyPercent':100}
    if existing and existing[0]['status']!='INACTIVE':
        ecs.update_service(cluster=o['Cluster'],service='aquanqa-api',taskDefinition=task,desiredCount=2,deploymentConfiguration=config)
    else:
        ecs.create_service(cluster=o['Cluster'],serviceName='aquanqa-api',taskDefinition=task,desiredCount=2,launchType='FARGATE',networkConfiguration=network(o),loadBalancers=[{'targetGroupArn':o['TargetGroup'],'containerName':'api','containerPort':8000}],healthCheckGracePeriodSeconds=120,deploymentConfiguration=config,enableECSManagedTags=True)
    save('api-task',{'arn':task,'database':db})
    print('API deployment started:',task,'database:',db)


def api_status(s):
    o=outputs(s)
    d=s.client('ecs').describe_services(cluster=o['Cluster'],services=['aquanqa-api'])['services'][0]
    print('desired/running/pending:',d['desiredCount'],d['runningCount'],d['pendingCount'])
    for deployment in d['deployments']: print(deployment['taskDefinition'],deployment.get('rolloutState'),deployment.get('rolloutStateReason',''))
    for e in d.get('events',[])[:5]: print(e['message'])
    print(s.client('elbv2').describe_target_health(TargetGroupArn=o['TargetGroup'])['TargetHealthDescriptions'])


def origin(s):
    alb=s.client('elbv2').describe_load_balancers(Names=[STACK])['LoadBalancers'][0]
    d=s.client('cloudfront').create_vpc_origin(VpcOriginEndpointConfig={
        'Name':STACK,'Arn':alb['LoadBalancerArn'],'HTTPPort':80,'HTTPSPort':443,
        'OriginProtocolPolicy':'http-only','OriginSslProtocols':{'Quantity':1,'Items':['TLSv1.2']},
    },Tags={'Items':[{'Key':'Project','Value':'aquanqa'}]})
    save('origin',{'id':d['VpcOrigin']['Id'],'host':alb['DNSName']})
    print('Private CloudFront origin:',d['VpcOrigin']['Id'],d['VpcOrigin']['Status'])


def edge(s):
    cf=s.client('cloudfront');vpc=load('origin');bucket=f'aquanqa-{ACCOUNT}-{REGION}-assets'
    status=cf.get_vpc_origin(Id=vpc['id'])['VpcOrigin']['Status']
    if status!='Deployed':
        print('VPC origin is',status,'; retry edge when Deployed');return
    oac=cf.create_origin_access_control(OriginAccessControlConfig={'Name':STACK,'Description':'Private Aquanqa static assets','SigningProtocol':'sigv4','SigningBehavior':'always','OriginAccessControlOriginType':'s3'})['OriginAccessControl']['Id']
    fn=cf.create_function(Name='aquanqa-spa-routing',FunctionConfig={'Comment':'Rewrite Angular client routes only; API behavior has no function','Runtime':'cloudfront-js-2.0'},FunctionCode=b"function handler(event) { var r = event.request; if (r.uri.indexOf('.') === -1) r.uri = '/index.html'; return r; }")
    pub=cf.publish_function(Name='aquanqa-spa-routing',IfMatch=fn['ETag'])
    cache={v['CachePolicy']['CachePolicyConfig']['Name']:v['CachePolicy']['Id'] for v in cf.list_cache_policies(Type='managed')['CachePolicyList']['Items']}
    request={v['OriginRequestPolicy']['OriginRequestPolicyConfig']['Name']:v['OriginRequestPolicy']['Id'] for v in cf.list_origin_request_policies(Type='managed')['OriginRequestPolicyList']['Items']}
    headers={v['ResponseHeadersPolicy']['ResponseHeadersPolicyConfig']['Name']:v['ResponseHeadersPolicy']['Id'] for v in cf.list_response_headers_policies(Type='managed')['ResponseHeadersPolicyList']['Items']}
    common={'ViewerProtocolPolicy':'redirect-to-https','Compress':True,'TrustedSigners':{'Enabled':False,'Quantity':0},'TrustedKeyGroups':{'Enabled':False,'Quantity':0},'ResponseHeadersPolicyId':headers['Managed-SecurityHeadersPolicy']}
    static={**common,'TargetOriginId':'assets','AllowedMethods':{'Quantity':2,'Items':['GET','HEAD'],'CachedMethods':{'Quantity':2,'Items':['GET','HEAD']}},'CachePolicyId':cache['Managed-CachingOptimized'],'FunctionAssociations':{'Quantity':1,'Items':[{'FunctionARN':pub['FunctionSummary']['FunctionMetadata']['FunctionARN'],'EventType':'viewer-request'}]}}
    api_behavior={**common,'ViewerProtocolPolicy':'https-only','TargetOriginId':'api','AllowedMethods':{'Quantity':7,'Items':['GET','HEAD','OPTIONS','PUT','PATCH','POST','DELETE'],'CachedMethods':{'Quantity':2,'Items':['GET','HEAD']}},'CachePolicyId':cache['Managed-CachingDisabled'],'OriginRequestPolicyId':request['Managed-AllViewerExceptHostHeader']}
    config={'CallerReference':STACK+'-20260914','Comment':'Aquanqa production frontend and API','Enabled':True,'DefaultRootObject':'index.html','PriceClass':'PriceClass_All','HttpVersion':'http2and3','IsIPV6Enabled':True,
        'Origins':{'Quantity':2,'Items':[
            {'Id':'assets','DomainName':bucket+'.s3.'+REGION+'.amazonaws.com','S3OriginConfig':{'OriginAccessIdentity':''},'OriginAccessControlId':oac},
            {'Id':'api','DomainName':vpc['host'],'VpcOriginConfig':{'VpcOriginId':vpc['id'],'OriginReadTimeout':60,'OriginKeepaliveTimeout':5}},
        ]},'DefaultCacheBehavior':static,
        'CacheBehaviors':{'Quantity':4,'Items':[{**api_behavior,'PathPattern':p} for p in ['/v1/*','/docs*','/openapi.json','/redoc*']]},
        'ViewerCertificate':{'CloudFrontDefaultCertificate':True},
    }
    d=cf.create_distribution(DistributionConfig=config)['Distribution']
    save('distribution',{'id':d['Id'],'domain':d['DomainName'],'arn':d['ARN']})
    # Keep the TLS-only policy and grant access exclusively to this distribution.
    policy=json.loads(s.client('s3').get_bucket_policy(Bucket=bucket)['Policy'])
    policy['Statement'].append({'Sid':'CloudFrontRead','Effect':'Allow','Principal':{'Service':'cloudfront.amazonaws.com'},'Action':'s3:GetObject','Resource':f'arn:aws:s3:::{bucket}/*','Condition':{'StringEquals':{'AWS:SourceArn':d['ARN']}}})
    s.client('s3').put_bucket_policy(Bucket=bucket,Policy=json.dumps(policy))
    print('HTTPS distribution created:',d['DomainName'],d['Status'])


def frontend(s):
    import mimetypes
    dist=ROOT/'frontend/dist/frontend/browser'
    if not (dist/'index.html').exists(): raise RuntimeError('Build Angular first')
    bucket=f'aquanqa-{ACCOUNT}-{REGION}-assets'
    for path in dist.rglob('*'):
        if not path.is_file(): continue
        key=path.relative_to(dist).as_posix()
        ctype=mimetypes.guess_type(key)[0] or 'application/octet-stream'
        if key.endswith('.js'): ctype='application/javascript'
        # Hashed application bundles can be cached indefinitely; the shell cannot.
        cache='public,max-age=31536000,immutable' if path.suffix in ['.js','.css'] and '-' in path.stem else 'no-cache'
        s.client('s3').upload_file(str(path),bucket,key,ExtraArgs={'ContentType':ctype,'CacheControl':cache})
    d=load('distribution')
    s.client('cloudfront').create_invalidation(DistributionId=d['id'],InvalidationBatch={'Paths':{'Quantity':1,'Items':['/*']},'CallerReference':str(__import__('time').time())})
    print('Frontend uploaded: https://'+d['domain'])


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['base','status','retry','build','build_status','setup','restore','restore_status','api','api_status','origin','edge','frontend'])
    a = p.parse_args()
    globals()[a.command](session())
