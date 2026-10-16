"""Project DocOps cleanup policy for the fixed Harbor Docker environment."""
from harbor.environments.docker.docker import DockerEnvironment


class DocOpsDockerEnvironment(DockerEnvironment):
    """Reuse Harbor lifecycle; delete compose resources while retaining images."""

    async def stop(self, delete: bool):
        await self.prepare_logs_for_host()
        command = ['down']
        if delete:
            command.extend(['--volumes', '--remove-orphans'])
        # Let the existing caller record failure/timeout and verify removal.
        await self._run_docker_compose_command(command)
