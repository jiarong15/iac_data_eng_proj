import pulumi
from pulumi_aws import s3, rds, route53
import pulumi_eks as eks
from pulumi_kubernetes.helm.v3 import Chart, ChartOpts, FetchOpts
import pulumi_kubernetes as k8s
from retrieve_secrets import get_secret
from s3_service_accounts import S3ServiceAccount
from traefik_route import TraefikRoute
 
ALL_SECRETS = get_secret()

cluster = eks.Cluster("ml-cluster",
                      create_oidc_provider=True)

mlflow_service_account = S3ServiceAccount(name='mlflow-service-account',
                                          args={'namespace': 'default',
                                                'oidcProvider': cluster.core.oidcProvider,
                                                'readOnly': False
                                          },
                                          opts=pulumi.ResourceOptions(provider=cluster._provider)
)

mlflowDB = rds.Instance("default",
                        allocated_storage=32,
                        db_name="mlflow-db",
                        engine="postgres",
                        engine_version="11.10",
                        instance_class=rds.InstanceType.T3_MICRO,
                        username=ALL_SECRETS["mlflow_rds_username"],
                        password=ALL_SECRETS["mlflow_rds_password"],
                        skip_final_snapshot=True,
                        vpc_security_group_ids=[cluster.node_security_group_id, cluster.cluster_security_group_id])

mlflow_artifact_store = s3.Bucket("mlflow-store",
                                  bucket="mflow-store-bucket",
                                  acl="public-read-write",
                                  tags={"Environment": "Dev"})

traefik = Chart(
    "traefik",
    ChartOpts(
        chart="traefik",
        version="20.2.1",
        # version="latest",
        fetch_opts=FetchOpts(
            repo="https://traefik.github.io/charts"
        )
    ), opts=pulumi.ResourceOptions(provider=cluster._provider)
)

mlflow = Chart(
    "mlflow",
    ChartOpts(
        chart="mlflow",
        fetch_opts=FetchOpts(
            repo="https://community-charts.github.io/helm-charts",
        ),
        values={
            "backendStore": {
                "postgres": {
                    "host": mlflowDB.address,
                    "port": mlflowDB.port,
                    "database": "mlflow",
                    "user": mlflowDB.username,
                    "password": mlflowDB.password
                }
            },
            "artifactRoot.s3.bucket": f"s3://{mlflow_artifact_store.bucket_domain_name}",
            "serviceAccount.name": mlflow_service_account.name,
            "serviceAccount.create": True
        }
    ),
    opts=pulumi.ResourceOptions(provider=cluster._provider)
)

TraefikRoute(name="mlflow-route",
             args={"namespace": "default",
                   "prefix": "/mlflow",
                   "service": mlflow.get_resource("v1/Service", "mlflow")
                  },
             opts=pulumi.ResourceOptions(provider=cluster._provider)
)

route53.Record("dns-record",
               zone_id=ALL_SECRETS["hosted_zone"],
               name="mlflow.jr25.com",
               type=route53.RecordType.CNAME,
               ttl=300,
               records=[traefik.get_resource('v1/Service', 'default/traefik').status.loadBalancer.ingress[0].hostname]
)

pulumi.export('bucket_name', mlflow_artifact_store.id)
pulumi.export("kubeconfig", cluster.kubeconfig)

