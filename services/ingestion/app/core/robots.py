import urllib.robotparser
import urllib.request
import ssl  # NEW
from urllib.parse import urlparse
import structlog

logger = structlog.get_logger(__name__)

class RobotChecker:
    def __init__(self):
        self.parsers = {} 
        
    def is_allowed(self, url, user_agent='*') -> bool:
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        if base_url not in self.parsers:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = f"{base_url}/robots.txt"
            try:
                req = urllib.request.Request(
                    robots_url, 
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0'}
                )
                
                # FIX: Disable SSL verification only for known broken certs
                ctx = ssl.create_default_context()
                if "stipendiumhungaricum.hu" in base_url:
                    logger.warning("ssl_bypass_active", url=base_url, reason="Known broken cert on hungarian govt server")
                    # TODO: Remove SSL bypass once stipendiumhungaricum.hu fixes their certificate
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                
                with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
                    rp.parse(response.read().decode("utf-8").splitlines())
                    
                self.parsers[base_url] = rp
                logger.info("fetched_robots_txt", url=robots_url)
            except Exception as e:
                logger.warning("failed_to_fetch_robots_txt", url=robots_url, error=str(e))
                self.parsers[base_url] = None
                
        rp = self.parsers[base_url]
        if rp is None:
            return True
            
        return rp.can_fetch(user_agent, url)

robot_checker = RobotChecker()