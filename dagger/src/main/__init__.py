"""Fedidevs Dagger CI/CD Pipeline"""
import dagger 
from typing import Annotated
from dagger import dag, function, object_type, Doc


@object_type
class Fedidevs:

    dir: Annotated[dagger.Directory, Doc("Directory containing source code")]
    flakytest_token: Annotated[dagger.Secret | None, Doc("API Token for https://flakytest.dev/")]
    
    def base(self) -> dagger.Container:
        """Return base image"""
        return (
            dag.container()
            .from_("python:3.12-alpine")
            .with_mounted_directory("/src", self.dir)
            .with_workdir("/src")
            .with_mounted_cache("/root/.cache/pip", dag.cache_volume("python-312"))
            .with_exec(["pip", "install", "-r", "requirements.txt"])
            .with_exec(["python", "manage.py", "collectstatic"])
        )

    @function
    def test(self) -> dagger.Container:
        """Run tests
        
        If FLAKYTEST_SECRET_TOKEN is set, we will send telemetry to https://flakytest.dev
        """
        if self.flakytest_token:
            return (
            self.base()
            .with_secret_variable("FLAKYTEST_SECRET_TOKEN", self.flakytest_token)
            .with_exec(["pytest"])
        )
        return (
            self.base()
            .with_exec(["pytest"]) 
        )

    @function
    # TODO implement this :p
    def deploy():
        pass

    @function 
    def ci(self) -> str:
        """Run entire CI pipeline"""
        # run tests 
        return self.test().stdout()
        # deploy 
