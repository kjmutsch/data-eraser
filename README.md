# Data Eraser

This project began because I'm sick of getting spam calls and I'm sick of companies using my data without explicit permission. There was a repo called Eraser that I forked from because they already accumulated data for 750+ data brokers. I used just that data, everything else in this repo is written by me and then Claude wrote the email templates.

Eraser was written in Go. It's email only with no browser automation, configs stored in config.yaml, runs once and then relies on dashboard for manual attention.

I wrote mine in Python, I use both an Email blast and Playwright form automation. I added priority and method fields to my broker list since Gmail rate limits to 250 emails/day so I could prioritize largest brokers first. I made 3 separate scripts because some brokers take time to respond. That way I can run the send.py script to send out the emails and then run the confirm.py script to check responses a few days later. 

Finally report.py sends a summary email in case I want to follow up with any unsuccessful attempts.


### What You'll Need

1. A **Gmail account** to send emails from

### Getting Started

## License

MIT

---

## Disclaimer

This tool sends legitimate data removal requests based on privacy laws. It's not legal advice. Not all brokers are required to comply with all requests, and response times vary.
