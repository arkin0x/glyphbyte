"""Deploy the symple web app on Modal: `modal deploy deploy/modal_app.py`.

The image installs this repository with the web extra; the bundled ONNX model ships
inside the package, so the endpoint needs no volume and no network."""

import modal

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("numpy", "opencv-python-headless", "onnxruntime", "fastapi", "uvicorn", "python-multipart")
    .add_local_dir("symple", remote_path="/root/symple")
)

app = modal.App("symple", image=image)


@app.function(cpu=2, memory=1024, min_containers=0, scaledown_window=300)
@modal.asgi_app()
def web():
    import sys
    sys.path.insert(0, "/root")
    from symple.web import create_app
    return create_app()
