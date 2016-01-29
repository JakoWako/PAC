import json
import urllib.request
import urllib.parse
import urllib.error
from openssl import *
from base64 import b64decode, b64encode
# Ceci est du code Python v3.x (la version >= 3.4 est conseillÃ©e pour une
# compatibilitÃ© optimale).
# --- les admins

class ServerError(Exception):
    """
    Exception dÃ©clenchÃ©e en cas de problÃ¨me cÃ´tÃ© serveur (URL incorrecte,
    accÃ¨s interdit, requÃªte mal formÃ©e, etc.)
    """
    def __init__(self, code=None, msg=None):
        self.code = code
        self.msg = msg


class Connection:
    """
    Cette classe sert Ã  ouvrir et Ã  maintenir une connection avec le systÃ¨me
    UGLIX. Voir les exemples ci-dessous.

    Pour crÃ©er une instance de la classe, il faut spÃ©cifier une ``adresse de 
    base''. Les requÃªtes se font Ã  partir de lÃ , ce qui est bien pratique.
    L'adresse de base est typiquement l'adresse du systÃ¨me UGLIX.

    Cet objet Connection() s'utilise surtout via ses mÃ©thodes get(), post()...

    Il est conÃ§u pour pouvoir Ãªtre Ã©tendu facilement. En dÃ©river une sous-classe
    capable de gÃ©rer des connexions chiffrÃ©es ne nÃ©cessite que 20 lignes de
    code supplÃ©mentaires.

    Exemple :
    >>> c = Connection("http://pac.fil.cool/uglix")
    >>> c.get('/bin/echo')
    'usage: echo [arguments]'
    """
    def __init__(self, base_url):
        self.base = base_url
        # au dÃ©part nous n'avons pas d'identifiant de session
        self.session = None

    def _post_processing(self, result, http_headers):
        """
        Effectue post-traitement sur le rÃ©sultat "brut" de la requÃªte. En
        particulier, on dÃ©code les dictionnaires JSON, et on converti le texte
        encodÃ© en UTF-8 en chaine de charactÃ¨re Unicode. On peut Ã©tendre Cette
        mÃ©thode pour gÃ©rer d'autres types de contenu si besoin.
        """
        if http_headers['Content-Type'] == "application/json":
            return json.loads(result.decode())
        if http_headers['Content-Type'].startswith("text/plain"):
            return result.decode()
        # on ne sait pas ce que c'est : on tel quel
        return result

    def _query(self, url, request, data=None):
        """
        Cette fonction Ã  usage interne est appelÃ©e par get(), post(), put(),
        etc. Elle reÃ§oit en argument une url et un
        """
        try:
            # si on a un identifiant de session, on le renvoie au serveur
            if self.session:
                request.add_header('Cookie', self.session)
            # lance la requÃªte. Si data n'est pas None, la requÃªte aura un
            # corps non-vide, avec data dedans.
            with urllib.request.urlopen(request, data) as connexion:
                # rÃ©cupÃ¨re les en-tÃªtes HTTP et le corps de la rÃ©ponse, puis
                # ferme la connection
                headers = dict(connexion.info())
                result = connexion.read()
            
            # si on envoie un identifiant de session, on le stocke
            if 'Set-Cookie' in headers:
                self.session = headers['Set-Cookie']

            # on effectue le post-processing, puis on renvoie les donnÃ©es.
            # c'est fini.
            return self._post_processing(result, headers)

        except urllib.error.HTTPError as e:
            # On arrive ici si le serveur a renvoyÃ© un code d'erreur HTTP
            # (genre 400, 403, 404, etc.). On rÃ©cupÃ¨re le corps de la rÃ©ponse
            # car il y a peut-Ãªtre des explications dedans. On a besoin des
            # en-tÃªte pour le post-processing.
            headers = dict(e.headers)
            message = e.read()
            raise ServerError(e.code, self._post_processing(message, headers)) from None
          
    
    def get(self, url):
        """
        Charge l'url demandÃ©e. Une requÃªte HTTP GET est envoyÃ©e.

        >>> c = Connection("http://pac.fil.cool/uglix")
        >>> c.get('/bin/echo')
        'usage: echo [arguments]'

        En cas d'erreur cÃ´tÃ© serveur, on rÃ©cupÃ¨re une exception.
        >>> c.get('/bin/foobar') # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        client.ServerError: (404, ...)
        """
        # prÃ©pare la requÃªte
        request = urllib.request.Request(self.base + url, method='GET')
        return self._query(url, request)


    def post(self, url, **kwds):
        """
        Charge l'URL demandÃ©e. Une requÃªte HTTP POST est envoyÃ©e. Il est 
        possible d'envoyer un nombre arbitraire d'arguments supplÃ©mentaires
        sous la forme de paires clef-valeur. Ces paires sont encodÃ©es sous la
        forme d'un dictionnaire JSON qui constitue le corps de la requÃªte.

        Python permet de spÃ©cifier ces paires clef-valeurs comme des arguments
        nommÃ©s de la mÃ©thode post(). On peut envoyer des valeurs de n'importe
        quel type sÃ©rialisable en JSON.

        Par exemple, pour envoyer un paramÃ¨tre nommÃ© "string_example" de valeur
        "toto et un paramÃ¨tre nommÃ© "list_example" de valeur [True, 42, {'foo': 'bar'}],
        il faut invoquer :

        >>> c = Connection("http://pac.fil.cool/uglix")
        >>> c.post('/bin/echo', string_example="toto", list_example=[True, 42, {'foo': 'bar'}])
        {'content_found': {'string_example': 'toto', 'list_example': [True, 42, {'foo': 'bar'}]}}

        L'idÃ©e la mÃ©thode post() convertit ceci en un dictionnaire JSON, qui 
        ici ressemblerait Ã  :

        {'string_example': 'toto', 'list_example': [True, 42, {'foo': 'bar'}]},

        puis l'envoie au serveur.
        """
        # prÃ©pare la requÃªte
        request = urllib.request.Request(self.base + url, method='POST')
        data = None
        # kwds est un dictionnaire qui contient les arguments nommÃ©s. S'il
        # n'est pas vide, on l'encode en JSON et on l'ajoute au corps de la
        # requÃªte.
        if kwds:     
            request.add_header('Content-type', 'application/json')
            data = json.dumps(kwds).encode()
        return self._query(url, request, data)


    def put(self, url, content):
        """
        Charge l'URL demandÃ©e avec une requÃªte HTTP PUT. L'argument content
        forme le corps de la requÃªte. Si content est de type str(), il est
        automatiquement encodÃ© en UTF-8. cf /doc/strings pour plus de dÃ©tails
        sur la question.
        """
        request = urllib.request.Request(self.base + url, method='PUT')
        if type(content) == str:
            content = content.encode()
        return self._query(url, request, data=content)


    def post_raw(self, url, data, content_type='application/octet-stream'):
        """
        Charge l'url demandÃ©e avec une requÃªte HTTP POST. L'argument data
        forme le corps de la requÃªte. Il doit s'agir d'un objet de type 
        bytes(). Cette mÃ©thode est d'un usage plus rare, et sert Ã  envoyer des
        donnÃ©es qui n'ont pas vocation Ã  Ãªtre serialisÃ©es en JSON (comme des
        donnÃ©es binaires chiffrÃ©es, par exemple).

        Principalement utilisÃ© pour Ã©tendre le client et lui ajouter des
        fonctionnalitÃ©.
        """
        request = urllib.request.Request(self.base + url, method='POST')
        request.add_header('Content-type', content_type)
        return self._query(url, request, data)
c = Connection("http://pac.fil.cool/uglix")
def doc(url):
	print(c.get('/doc/'+url))
def connect():
	print(c.post('/bin/login',user='estamm',password='UPWxrX3FHq'))
def inbox():
	print(c.get('/home/estamm/INBOX'))
def message(nb):
	print(c.get('/home/estamm/INBOX/'+nb))
def getmessage(nb):
	return c.get('/home/estamm/INBOX/'+nb+'/body')
def cat(lien):
	c.get('/home/estamm/'+lien)
def connectCHAP():
	mychallenge = c.get('/bin/login/CHAP')
	print(mychallenge)
	plaintext = 'estamm-'+mychallenge['challenge']
	c.post('/bin/login/CHAP',user='estamm',response=encrypt(plaintext,'UPWxrX3FHq','aes-128-cbc'))
def sendmail(dest,subject,content):
	print(c.post('/bin/sendmail',to=dest,subject=subject,content=content))
def tickets():
	print(c.get('/bin/crypto_helpdesk'))
def show_ticket(nb):
	print(c.get('/bin/crypto_helpdesk/ticket/'+nb))
def ticket_attachment(nb,name):
	return c.get('/bin/crypto_helpdesk/ticket/'+nb+'/attachment/'+name)
def closeticket(nb):
	print(c.post('/bin/crypto_helpdesk/ticket/'+nb+'/close',confirm=True))
def answerticket():
	fileattach = c.get('/bin/crypto_helpdesk/ticket/59/attachment/file')
	result = encrypt(fileattach,'GjN&+GD*gZ','aes-128-cbc')
	print(result)
	sendmail('bmohr','toto',result)
def answerticket60():
	f = open('dechiffre2.txt','r')
	x = f.read()
	sendmail('farrah04','ticket60',x)
def answerticket90():
	'''attachment = c.get('/bin/crypto_helpdesk/ticket/90/attachment/message')'''
	'''publickey = print(c.get('/bin/crypto_helpdesk/ticket/90/attachment/public-key'))'''
	f = open('resultat2.txt','rb')
	sendmail('scottie70','ticket90',(b64encode(f.read())).decode())
def answerticket91():
	publickey =c.get('/bin/finger/icey27/pk')
	f = open('ticket91.txt','w')
	write = f.write(publickey)
	chaine = "informations sensibles"
	f.close()
	adresse = c.get('/bin/crypto_helpdesk/ticket/91/attachment/contact')
	x = encryptRSA(chaine,"ticket91.txt")
	sendmail(adresse,"ticket91",x)
def answerticket912():
	mail = c.get('/home/estamm/INBOX/3090/body')
	'''f = open("privatekey.ssl",'r')'''
	x = decryptRSA(b64decode(mail))
	sendmail('donat50','ticket91',x)
def dlsoundtrack():
	soundtrack = c.get('/home/estamm/soundtrack_1.s3m')
	f = open('soundtrack_1.s3m','w')
	f.write((b64encode(soundtrack).decode()))
	f.close()
	print('OK')
def createpublickey():
	f = open("mypublickey.ssl",'r')
	c.put('/home/estamm/.pk.email.openssl',f.read())
	f.close()
def getpublickey(name):
	return c.get('/bin/finger/'+name+'/pk')
def answerticket92():
	hiscontent = ticket_attachment('92','reciprocity')
	hisid = ticket_attachment('92','contact')
	enccontent = encrypt(hiscontent,'hypersecret42keyofthed34d')
	hispk = getpublickey('epadberg')
	f = open("pk92",'w')
	f.write(hispk)
	f.close()
	result = encryptRSA('hypersecret42keyofthed34d','pk92')
	dico = {'skey':result,'document':enccontent}
	sendmail(hisid,'ticket92',dico)
def signercontrattravail():
	contrat = getmessage('3223')
	f = open("privatekey.ssl",'r') 
	resultat = sign('privatekey.ssl',contrat)
	sendmail('droberts','contrat',resultat)
	
