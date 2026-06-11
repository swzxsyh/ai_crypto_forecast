"""命令行入口。

业务逻辑已经拆到 crypto_predictor 包中；保留 main.py 是为了继续支持：
    python main.py predict --symbol BTC/USDT
"""

from crypto_predictor.cli import main


if __name__ == "__main__":
    main()
