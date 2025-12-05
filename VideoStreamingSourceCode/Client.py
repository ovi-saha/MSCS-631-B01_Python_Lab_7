from tkinter import *
import tkinter.messagebox as tkMessageBox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os
import time # <-- ADDED FOR DATA RATE CALCULATION

from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class Client:
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    SETUP = 0
    PLAY = 1
    PAUSE = 2
    TEARDOWN = 3
    
    # Initiation..
    def __init__(self, master, serveraddr, serverport, rtpport, filename):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.handler)
        self.createWidgets()
        self.serverAddr = serveraddr
        self.serverPort = int(serverport)
        self.rtpPort = int(rtpport)
        self.fileName = filename
        self.rtspSeq = 0
        self.sessionId = 0
        self.requestSent = -1
        self.teardownAcked = 0
        self.connectToServer()
        self.frameNbr = 0
        
        # ADDED FOR DATA RATE CALCULATION:
        self.totalPayloadBytes = 0
        self.startTime = 0.0
        self.stopTime = 0.0

    def createWidgets(self):
        """Build GUI."""
        # Create Setup button
        self.setup = Button(self.master, width=20, padx=3, pady=3)
        self.setup["text"] = "Setup"
        self.setup["command"] = self.setupMovie
        self.setup.grid(row=1, column=0, padx=2, pady=2)

        # Create Play button
        self.start = Button(self.master, width=20, padx=3, pady=3)
        self.start["text"] = "Play"
        self.start["command"] = self.playMovie
        self.start.grid(row=1, column=1, padx=2, pady=2)

        # Create Pause button
        self.pause = Button(self.master, width=20, padx=3, pady=3)
        self.pause["text"] = "Pause"
        self.pause["command"] = self.pauseMovie
        self.pause.grid(row=1, column=2, padx=2, pady=2)

        # Create Teardown button
        self.teardown = Button(self.master, width=20, padx=3, pady=3)
        self.teardown["text"] = "Teardown"
        self.teardown["command"] = self.exitClient
        self.teardown.grid(row=1, column=3, padx=2, pady=2)

        # Create a label to display the movie
        self.label = Label(self.master, height=19)
        self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5)

    def setupMovie(self):
        """Setup button handler."""
        if self.state == self.INIT:
            self.sendRtspRequest(self.SETUP)

    def exitClient(self):
        """Teardown button handler. Includes Data Rate calculation."""
        self.sendRtspRequest(self.TEARDOWN)
        
        # CALCULATE AND PRINT DATA RATE
        if self.stopTime > self.startTime:
            streamingTime = self.stopTime - self.startTime
            dataRateBps = self.totalPayloadBytes / streamingTime
            
            print(f"\n--- Statistics ---")
            print(f"Total Payload Bytes Received: {self.totalPayloadBytes:,} bytes")
            print(f"Total Streaming Time: {streamingTime:.2f} seconds")
            print(f"Video Data Rate: {dataRateBps:.2f} Bytes/sec")
            print(f"Video Data Rate: {dataRateBps * 8 / 1000000:.2f} Mbps")
            print(f"------------------")
            
        self.master.destroy() # Close the gui window
        try:
            # Delete the cache image from video
            os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)
        except:
            pass 

    def pauseMovie(self):
        """Pause button handler."""
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)

    def playMovie(self):
        """Play button handler."""
        if self.state == self.READY:
            # Must define playEvent before starting the thread
            self.playEvent = threading.Event()
            self.playEvent.clear()
            threading.Thread(target=self.listenRtp).start()
            self.sendRtspRequest(self.PLAY)

    def listenRtp(self):
        """Listen for RTP packets and track data rate."""
        while True:
            try:
                data = self.rtpSocket.recv(20480)
                if data:
                    rtpPacket = RtpPacket()
                    rtpPacket.decode(data)

                    currFrameNbr = rtpPacket.seqNum()
                    print("Current Seq Num: " + str(currFrameNbr))

                    if currFrameNbr > self.frameNbr: # Discard the late packet
                        
                        # --- DATA RATE TRACKING LOGIC ---
                        if self.startTime == 0.0:
                            self.startTime = time.time() # Start timer on first packet
                            
                        self.totalPayloadBytes += len(rtpPacket.getPayload()) # Track bytes
                        self.stopTime = time.time() # Update stop time with every received packet
                        # --------------------------------
                        
                        self.frameNbr = currFrameNbr
                        self.updateMovie(self.writeFrame(rtpPacket.getPayload()))
            except:
                # Stop listening upon requesting PAUSE or TEARDOWN (timeout)
                if self.playEvent.isSet():
                    break

                # Upon receiving ACK for TEARDOWN request, close the RTP socket
                if self.teardownAcked == 1:
                    try:
                        self.rtpSocket.shutdown(socket.SHUT_RDWR)
                        self.rtpSocket.close()
                    except:
                        pass
                    break

    def writeFrame(self, data):
        """Write the received frame to a temp image file. Return the image file."""
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        file = open(cachename, "wb")
        file.write(data)
        file.close()
        return cachename

    def updateMovie(self, imageFile):
        """Update the image file as video frame in the GUI."""
        photo = ImageTk.PhotoImage(Image.open(imageFile))
        self.label.configure(image = photo, height=288)
        self.label.image = photo

    def connectToServer(self):
        """Connect to the Server. Start a new RTSP/TCP session."""
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
        except:
            tkMessageBox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)

    def sendRtspRequest(self, requestCode):
        """Send RTSP request to the server."""
        request = ''
        
        # Setup request
        if requestCode == self.SETUP and self.state == self.INIT:
            threading.Thread(target=self.recvRtspReply).start()
            self.rtspSeq += 1
            
            # Request line, CSeq, and Transport header
            request = 'SETUP ' + self.fileName + ' RTSP/1.0\n'
            request += 'CSeq: ' + str(self.rtspSeq) + '\n'
            request += 'Transport: RTP/UDP; client_port= ' + str(self.rtpPort)
            
            self.requestSent = self.SETUP
            
        # Play request
        elif requestCode == self.PLAY and self.state == self.READY:
            self.rtspSeq += 1
            
            # Request line, CSeq, and Session header
            request = 'PLAY ' + self.fileName + ' RTSP/1.0\n'
            request += 'CSeq: ' + str(self.rtspSeq) + '\n'
            request += 'Session: ' + str(self.sessionId)

            self.requestSent = self.PLAY
            
        # Pause request
        elif requestCode == self.PAUSE and self.state == self.PLAYING:
            self.rtspSeq += 1
            
            # Request line, CSeq, and Session header
            request = 'PAUSE ' + self.fileName + ' RTSP/1.0\n'
            request += 'CSeq: ' + str(self.rtspSeq) + '\n'
            request += 'Session: ' + str(self.sessionId)
            
            self.requestSent = self.PAUSE
            
        # Teardown request
        elif requestCode == self.TEARDOWN and not self.state == self.INIT:
            self.rtspSeq += 1
            
            # Request line, CSeq, and Session header
            request = 'TEARDOWN ' + self.fileName + ' RTSP/1.0\n'
            request += 'CSeq: ' + str(self.rtspSeq) + '\n'
            request += 'Session: ' + str(self.sessionId)
            
            self.requestSent = self.TEARDOWN
            
        else:
            if self.rtspSeq > 0:
                self.rtspSeq -= 1 
            return

        # Send the RTSP request using rtspSocket.
        try:
            self.rtspSocket.send(request.encode())
            print('\nData sent:\n' + request)
        except:
            print("Connection Error: Could not send RTSP request.")

    def recvRtspReply(self):
        """Receive RTSP reply from the server."""
        while True:
            try:
                reply = self.rtspSocket.recv(1024)
                if reply:
                    self.parseRtspReply(reply.decode("utf-8"))
            except:
                pass 

            # Close the RTSP socket upon receiving Teardown ACK
            if self.teardownAcked == 1:
                try:
                    self.rtspSocket.shutdown(socket.SHUT_RDWR)
                    self.rtspSocket.close()
                except:
                    pass
                break

    def parseRtspReply(self, data):
        """Parse the RTSP reply from the server."""
        lines = data.split('\n')
        
        # Check Status code (line 0)
        statusCode = int(lines[0].split(' ')[1])
        
        # Check CSeq (line 1)
        seqNum = int(lines[1].split(' ')[1])

        if seqNum == self.rtspSeq:
            
            sessionLine = [line for line in lines if line.startswith("Session:")]
            session = 0
            if sessionLine:
                try:
                    session = int(sessionLine[0].split(' ')[1])
                except:
                    pass
            
            if self.sessionId == 0 and session != 0:
                self.sessionId = session
            
            if self.sessionId == session or self.requestSent == self.SETUP:
                if statusCode == 200:
                    if self.requestSent == self.SETUP:
                        self.state = self.READY
                        self.openRtpPort()
                    elif self.requestSent == self.PLAY:
                        self.state = self.PLAYING
                    elif self.requestSent == self.PAUSE:
                        self.state = self.READY
                        self.playEvent.set()
                    elif self.requestSent == self.TEARDOWN:
                        self.state = self.INIT
                        self.teardownAcked = 1
                
                elif statusCode == 404:
                    print("RTSP Error: 404 FILE_NOT_FOUND")
                elif statusCode == 500:
                    print("RTSP Error: 500 CONNECTION_ERROR")

    def openRtpPort(self):
        """Open RTP socket binded to a specified port."""
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 
        self.rtpSocket.settimeout(0.5)

        try:
            # Bind the socket to the local machine ("") using the RTP port
            self.rtpSocket.bind(("", self.rtpPort)) 
        except:
            tkMessageBox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort)

    def handler(self):
        """Handler on explicitly closing the GUI window."""
        self.pauseMovie()
        if tkMessageBox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()
        else:
            if self.state == self.READY:
                self.playMovie()