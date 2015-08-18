var index = lunr(function () {
    this.field('title', {boost: 10});
    this.field('tags', {boost: 30});
    this.ref('id');
})

{% for question in questions %}
index.add({
    id: {{ question.Id }},
    title: "{{ question.Title | clean }}",
    body: '{% for tag in question.Tags %}{{ tag }} {% endfor %}'
});
{% endfor %}
