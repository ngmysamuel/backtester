import os
import queue
import threading
from datetime import datetime
from time import sleep

import pandas as pd
from transformers import pipeline

from backtester.data.data_handler import DataHandler
from backtester.events.event import Event
from backtester.util.util import str_to_seconds, SentimentTuple
from collections import defaultdict

class NewsDataHandler(DataHandler):
    def __init__(self, event_queue: queue.Queue[Event], **kwargs):
        """
        Initializes the YFDataHandler
        args:
            event_queue: the Event Queue
            start_date: start date of the backtest
            end_date: end date of the backtest
            symbol_list: a list of symbol strings
            interval: e.g. 5m means OHLC data for 5 minutes
            exchange_closing_time: 24h time format - HH:MM
        """
        self.event_queue = event_queue
        self.period = str_to_seconds(kwargs["period"])
        self.symbol_list: str = kwargs["symbol_list"]
        self.keyword_dict: dict[str, list[str]] = kwargs["keyword_dict"]
        self.sentiment_interval: str = str_to_seconds(kwargs["sentiment_interval"])
        self.base_url = "https://newsapi.org/v2/top-headlines"
        self.api_key = os.getenv('NEWS_API')

        self.beginning_time = datetime.now().timestamp()
        self.start_time = self.beginning_time
        self.end_time = self.start_time + self.sentiment_interval - 1
        self.final_time = self.start_time + self.period

        self.pipe = pipeline("text-classification", model=kwargs["model"])
        self.seen_articles: dict[str, int] = {} # {articledesc: 1 / -1}
        self._symbol_data: dict[str, list[SentimentTuple]] = defaultdict(list) # {ticker: [(timestamp: xxx, sentiment_score: xxx), (...)]}

        self._thread = threading.Thread(target=self._poll_and_process)
        self._thread.daemon = True
        self._thread.start()

    def _poll_and_process(self):
        print("Polling for sentiments...")
        while self.start_time < self.final_time:
            sleep_time = self.end_time - datetime.now().timestamp()
            if sleep_time > 0:
                sleep(sleep_time)
            for ticker in self.symbol_list:
                keyword_list = self.keyword_dict[ticker]
                articles, total_results, page_number = [], 100, 1
                while len(articles) < total_results:
                    # req = requests.get(self.base_url, params={"q": " OR ".join(keyword_list), "category": "business", "pageSize": 100, "page": page_number}, headers={"Authorization": self.api_key})
                    # print(req.url)
                    # resp = req.json()
                    resp = {'status': 'ok', 'totalResults': 2, 'articles': [{'source': {'id': 'fortune', 'name': 'Fortune'}, 'author': 'Jim Edwards', 'title': 'Michael Saylor’s Strategy flirts again with the danger threshold at which his company is worth less than his Bitcoin - Fortune', 'description': 'Why hold a stock that is worth less than the underlying asset it represents?', 'url': 'https://fortune.com/2026/01/02/michael-saylor-strategy-mnav-bitcoin/', 'urlToImage': 'https://fortune.com/img-assets/wp-content/uploads/2025/10/GettyImages-2217059347-e1761011704696.jpg?resize=1200,600', 'publishedAt': '2026-01-02T16:10:00Z', 'content': 'Stock in Michael Saylors Bitcoin treasury company, Strategy, was up 1.22% in early trading today, giving the company a brief period of relief. The stock has declined 66% since its high last July, and… [+2611 chars]'}, {'source': {'id': None, 'name': 'NPR'}, 'author': 'Rafael Nam', 'title': 'Crypto soared in 2025 — and then crashed. Now what? - NPR', 'description': 'For most of 2025, cryptocurrencies such as bitcoin surged as President Trump vowed to make the U.S. a crypto leader. But now, a severe sell-off has shaken the sector.', 'url': 'https://www.npr.org/2026/01/01/nx-s1-5642654/trump-crypto-winter-bitcoin', 'urlToImage': 'https://npr.brightspotcdn.com/dims3/default/strip/false/crop/5667x3188+0+178/resize/1400/quality/100/format/jpeg/?url=http%3A%2F%2Fnpr-brightspot.s3.amazonaws.com%2F43%2F94%2Feeeff2a44e2fb7a81ce417dcd254%2Fgettyimages-2231710765.jpg', 'publishedAt': '2026-01-01T10:00:00Z', 'content': 'This was supposed to be crypto\'s year.\r\nPresident Trump got elected vowing to make the U.S. "the crypto capital of the world\r\n" and by many measures, he delivered.\r\nFrom the crypto-friendly regulator… [+8406 chars]'}]}
                    if resp["status"] != "ok":
                        raise ValueError(resp)
                    total_results = resp["totalResults"]
                    articles.extend(resp["articles"])
                    page_number += 1
                total_articles = consolidated_sentiment = 0

                new_articles, texts, old_scores = [], [], []
                for article in articles:
                    key = f"{article['title']}_{article['description']}_{article['source']['name']}"
                    if key not in self.seen_articles:
                        new_articles.append(article)
                        texts.append(f"{article['title']} {article['description']}")
                    else:
                        old_scores.append(self.seen_articles[key])

                model_output = self.pipe(texts)
                scores = [1 if o["label"] == "positive" else -1 for o in model_output if o["score"] > 0.5 and o["label"] != "neutral"]
                self.seen_articles = self.seen_articles | {f"{article['title']}_{article['description']}_{article['source']['name']}": score for text, score in zip(new_articles, scores)}

                consolidated_sentiment = sum(scores) + sum(old_scores)
                total_articles = len(scores) + len(old_scores)

                if total_articles > 0:
                    self._symbol_data[ticker].append(SentimentTuple(Index=pd.to_datetime(self.start_time, unit='s'), score=consolidated_sentiment/total_articles))
                elif total_articles == 0:
                    if self._symbol_data[ticker]:
                        self._symbol_data[ticker].append(self._symbol_data[ticker][-1].copy())
                    else:
                        self._symbol_data[ticker].append(SentimentTuple(Index=pd.to_datetime(self.start_time, unit='s'), score=0))

            print(f"Timestamp (sentiments):: {self.start_time} <> {self.end_time} ")
            self.start_time = self.end_time + 1
            self.end_time = self.start_time + self.sentiment_interval - 1

    def get_latest_bars(self, symbol: str, n: int = 1) -> list[SentimentTuple]:
        """
            Default get the last 1 data which represents the latest data; else the last n data points.
            If there is no data, set the as of time to NOW and the sentiment to 0 representing a neutral view point
        """
        if symbol in self._symbol_data:
            return self._symbol_data[symbol][-n:]
        return [SentimentTuple(Index=datetime.now(), score=0.0)]

    def update_bars(self):
        pass