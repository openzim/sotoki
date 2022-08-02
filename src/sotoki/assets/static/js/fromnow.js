/* replace <time class="fromnow" /> with human delta between `datetime` attr and now */
document.addEventListener('DOMContentLoaded', function(){
    var time_elements = document.querySelectorAll("time.fromnow");
    for (var i=0; i<time_elements.length; i++) {
        time_elements[i].innerHTML = moment(time_elements[i].getAttribute("datetime")).fromNow();
    }
});
