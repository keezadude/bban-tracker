import argparse


def _parse_args():
    p = argparse.ArgumentParser(description="Launch BBAN Tracker GUI")
    p.add_argument("--dev", action="store_true", help="Use webcam (development mode) instead of RealSense")
    p.add_argument("--src", type=int, default=0, help="Camera index when --dev is supplied (default 0)")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    from gui.main_gui import launch

    launch(dev_mode=args.dev, cam_src=args.src) 