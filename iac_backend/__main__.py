import pulumi
from pulumi_aws import s3, rds
import pulumi_eks as eks
from pulumi_kubernetes.helm.v3 import Chart, ChartOpts, FetchOpts
from retrieve_secrets import get_secret

 
ALL_SECRETS = get_secret()

cluster = eks.Cluster("ml-cluster",
                      create_oidc_provider=True)

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
        fetch_opts=FetchOpts(
            repo="https://traefik.github.io/charts",
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
            "artifactRoot.s3.bucket": f"s3://{mlflow_artifact_store.bucket_domain_name}"
        }
    ),
    opts=pulumi.ResourceOptions(provider=cluster._provider)
)

pulumi.export('bucket_name', mlflow_artifact_store.id)
pulumi.export("kubeconfig", cluster.kubeconfig)

