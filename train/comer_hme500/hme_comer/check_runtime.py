"""Fail before downloads/training if the installed W&B/Protobuf pair is incompatible."""
import importlib.metadata as metadata
import json


def check():
    from packaging.requirements import Requirement
    versions={name:metadata.version(name) for name in ('wandb','protobuf')}
    # This intentionally imports the symbol from the user's failing traceback.
    try:
        import wandb
        import google.protobuf
        from wandb.proto.wandb_telemetry_pb2 import Imports
        assert Imports is not None
    except ImportError as exc:
        raise RuntimeError('W&B/Protobuf import failed. Run setup with the current requirements.txt '
                           'in a fresh Python process; remove the old wandb==0.22.3 notebook install.') from exc
    if versions['protobuf']!=google.protobuf.__version__ or versions['wandb']!=wandb.__version__:
        raise RuntimeError('Loaded modules differ from installed packages; restart the notebook kernel.')
    for package in ('wandb','grpcio-tools'):
        try: requirements=metadata.requires(package) or []
        except metadata.PackageNotFoundError: continue
        for text in requirements:
            req=Requirement(text)
            if req.name=='protobuf' and (not req.marker or req.marker.evaluate()):
                if versions['protobuf'] not in req.specifier:
                    raise RuntimeError(f'{package} requires {req}; installed protobuf={versions["protobuf"]}. '
                                       'Install the current requirements.txt before training.')
    return versions


if __name__=='__main__': print('W&B runtime ready:',json.dumps(check()))
